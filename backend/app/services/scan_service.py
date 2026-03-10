"""Scan lifecycle management service.

Handles creation, retrieval, listing, cancellation, and deletion of scans.
Dispatches Celery tasks for asynchronous pipeline execution.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.base import PhaseStatus, ScanStatus
from app.models.scan import Scan, ScanPhase

logger = logging.getLogger(__name__)

# Phase definitions: (phase_number, phase_name)
PIPELINE_PHASES = [
    (1, "recon"),
    (2, "network"),
    (3, "vulnscan"),
    (4, "report"),
]


async def create_scan(
    db: AsyncSession,
    target_domain: str,
    config: dict[str, Any],
    user_id: int,
) -> Scan:
    """Create a new scan record with 4 phase records, then dispatch the Celery task.

    Generates a scan_uid like ``scan_{timestamp}`` and sets results_dir to
    ``/results/scan_{uid}/``.
    """
    scan_uid = f"scan_{int(time.time())}"
    results_dir = f"/results/{scan_uid}/"

    scan = Scan(
        scan_uid=scan_uid,
        target_domain=target_domain,
        status=ScanStatus.PENDING,
        current_phase=0,
        config=config,
        results_dir=results_dir,
        created_by=user_id,
    )
    db.add(scan)
    await db.flush()  # Populate scan.id

    # Create phase records
    for phase_number, phase_name in PIPELINE_PHASES:
        phase = ScanPhase(
            scan_id=scan.id,
            phase_number=phase_number,
            phase_name=phase_name,
            status=PhaseStatus.PENDING,
            tool_statuses={},
        )
        db.add(phase)

    await db.commit()
    await db.refresh(scan)

    # Dispatch Celery task (pipeline-eng will create the task module)
    try:
        from app.tasks.scan_tasks import run_scan_task

        run_scan_task.delay(scan.id)
        logger.info("Dispatched scan task for scan_id=%d (%s)", scan.id, scan_uid)
    except ImportError:
        logger.warning(
            "scan_tasks module not available yet; scan %d created but task not dispatched",
            scan.id,
        )
    except Exception:
        logger.exception("Failed to dispatch Celery task for scan %d", scan.id)

    return scan


async def get_scan(db: AsyncSession, scan_id: int) -> Scan | None:
    """Return a scan with its phases eagerly loaded, or None if not found."""
    result = await db.execute(
        select(Scan)
        .where(Scan.id == scan_id)
        .options(selectinload(Scan.phases))
    )
    return result.scalar_one_or_none()


async def list_scans(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    status_filter: ScanStatus | None = None,
) -> tuple[list[Scan], int]:
    """Return a paginated list of scans and the total count.

    Results are ordered by creation time descending (newest first).
    """
    query = select(Scan).options(selectinload(Scan.phases))

    if status_filter is not None:
        query = query.where(Scan.status == status_filter)

    # Count total
    count_query = select(func.count()).select_from(Scan)
    if status_filter is not None:
        count_query = count_query.where(Scan.status == status_filter)
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Paginate
    offset = (page - 1) * per_page
    query = query.order_by(Scan.created_at.desc()).offset(offset).limit(per_page)

    result = await db.execute(query)
    scans = list(result.scalars().all())

    return scans, total


async def cancel_scan(db: AsyncSession, redis_client: Any, scan_id: int) -> Scan | None:
    """Cancel a running scan by setting a Redis cancellation flag.

    The pipeline engine checks ``scan_cancel:{scan_id}`` on each phase boundary.
    Also updates the database status to CANCELLED.
    """
    scan = await get_scan(db, scan_id)
    if scan is None:
        return None

    if scan.status in (ScanStatus.PENDING, ScanStatus.RUNNING):
        # Set Redis cancellation flag
        await redis_client.set(f"scan_cancel:{scan_id}", "1", ex=3600)
        logger.info("Set cancellation flag for scan %d", scan_id)

        scan.status = ScanStatus.CANCELLED
        scan.error_message = "Cancelled by user"
        await db.commit()
        await db.refresh(scan)

    return scan


async def delete_scan(db: AsyncSession, scan_id: int) -> bool:
    """Delete a scan record and all associated data.

    Returns True if the scan was found and deleted, False otherwise.
    """
    scan = await get_scan(db, scan_id)
    if scan is None:
        return False

    await db.delete(scan)
    await db.commit()
    logger.info("Deleted scan %d", scan_id)
    return True


async def retry_scan(db: AsyncSession, scan_id: int) -> Scan | None:
    """Retry a failed scan by resetting its status and dispatching a new Celery task.

    Only scans in FAILED status can be retried.
    """
    scan = await get_scan(db, scan_id)
    if scan is None:
        return None

    if scan.status != ScanStatus.FAILED:
        return None

    # Reset scan status
    scan.status = ScanStatus.PENDING
    scan.current_phase = 0
    scan.error_message = None
    scan.started_at = None
    scan.completed_at = None

    # Reset all phase statuses
    for phase in scan.phases:
        phase.status = PhaseStatus.PENDING
        phase.started_at = None
        phase.completed_at = None
        phase.duration_seconds = None
        phase.error_message = None
        phase.log_output = None
        phase.tool_statuses = {}

    await db.commit()
    await db.refresh(scan)

    # Dispatch Celery task
    try:
        from app.tasks.scan_tasks import run_scan_task

        run_scan_task.delay(scan.id)
        logger.info("Dispatched retry task for scan_id=%d", scan.id)
    except ImportError:
        logger.warning("scan_tasks module not available; retry for scan %d not dispatched", scan.id)
    except Exception:
        logger.exception("Failed to dispatch retry Celery task for scan %d", scan.id)

    return scan


async def get_scan_logs(db: AsyncSession, scan_id: int) -> list[dict[str, Any]]:
    """Aggregate log output from all phases of a scan.

    Returns a list of dicts with phase_number, phase_name, and log_output.
    """
    scan = await get_scan(db, scan_id)
    if scan is None:
        return []

    logs: list[dict[str, Any]] = []
    for phase in scan.phases:
        logs.append(
            {
                "phase_number": phase.phase_number,
                "phase_name": phase.phase_name,
                "status": phase.status.value if phase.status else "unknown",
                "log_output": phase.log_output or "",
                "error_message": phase.error_message or "",
            }
        )

    return logs
