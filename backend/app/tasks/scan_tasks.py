"""Celery task definitions for scan execution.

The main entry point is ``run_scan_task`` which is dispatched by the API
when a new scan is created.  It creates a :class:`PipelineEngine` and
runs the full 4-phase pipeline inside ``asyncio.run()``.
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback

from app.core.exceptions import ToolExecutionError
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
    track_started=True,
)
def run_scan_task(self, scan_id: int) -> dict:
    """Execute the full scan pipeline for the given *scan_id*.

    This task runs inside a Celery worker process.  It creates a fresh
    asyncio event loop (``asyncio.run``) to execute the async
    ``PipelineEngine.run()`` method.

    On transient ``ToolExecutionError`` failures the task will retry
    up to ``max_retries`` times.

    Task configuration:
    - ``acks_late=True``: Message is acknowledged after task completes,
      so if the worker crashes the task will be re-delivered.
    - ``reject_on_worker_lost=True``: If the worker process is killed,
      the message is requeued.
    - ``track_started=True``: Celery will record when the task starts.
    """
    attempt = self.request.retries + 1
    logger.info(
        "Starting scan task for scan_id=%d (attempt %d/%d, task_id=%s)",
        scan_id,
        attempt,
        self.max_retries + 1,
        self.request.id,
    )
    start_time = time.monotonic()

    try:
        asyncio.run(_run_pipeline(scan_id))
        elapsed = time.monotonic() - start_time
        logger.info(
            "Scan task completed successfully: scan_id=%d, duration=%.1fs",
            scan_id,
            elapsed,
        )
        return {"scan_id": scan_id, "status": "completed", "duration_seconds": round(elapsed, 1)}

    except ToolExecutionError as exc:
        elapsed = time.monotonic() - start_time
        logger.warning(
            "ToolExecutionError for scan %d (attempt %d/%d, %.1fs elapsed) — "
            "tool=%s exit=%d: %s",
            scan_id,
            attempt,
            self.max_retries + 1,
            elapsed,
            exc.tool,
            exc.exit_code,
            str(exc)[:500],
        )
        if attempt <= self.max_retries:
            logger.info("Retrying scan %d in %ds...", scan_id, self.default_retry_delay)
            raise self.retry(exc=exc)
        else:
            logger.error("All retries exhausted for scan %d — marking as failed", scan_id)
            asyncio.run(_mark_scan_failed(scan_id, f"All retries exhausted: {exc}"))
            return {"scan_id": scan_id, "status": "failed", "error": str(exc)[:500]}

    except Exception as exc:
        elapsed = time.monotonic() - start_time
        tb = traceback.format_exc()
        logger.exception(
            "Unrecoverable error in scan %d (attempt %d/%d, %.1fs elapsed): %s\n%s",
            scan_id,
            attempt,
            self.max_retries + 1,
            elapsed,
            str(exc)[:500],
            tb[-2000:],
        )
        # Mark scan as failed via a quick async call
        try:
            asyncio.run(_mark_scan_failed(scan_id, str(exc)))
        except Exception as mark_exc:
            logger.error(
                "Failed to mark scan %d as failed in DB: %s",
                scan_id,
                mark_exc,
            )
        return {
            "scan_id": scan_id,
            "status": "failed",
            "error": str(exc)[:500],
            "exception_type": type(exc).__name__,
        }


async def _run_pipeline(scan_id: int) -> None:
    """Instantiate the engine and run the pipeline."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings
    from app.pipeline.engine import PipelineEngine

    # Create a fresh engine bound to the current event loop.
    # The module-level engine in app.database is tied to a different loop —
    # each asyncio.run() in the Celery task creates a new loop, so we must
    # not reuse the module-level connection pool across calls.
    db_engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    pipeline = PipelineEngine(scan_id=scan_id, db_session_factory=session_factory)
    try:
        await pipeline.run()
    finally:
        pipeline.close()
        await db_engine.dispose()


async def _mark_scan_failed(scan_id: int, error_message: str) -> None:
    """Last-resort helper to mark a scan as failed in the DB.

    Called when the pipeline raises an unrecoverable exception and
    the engine itself did not manage to update the scan status.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings
    from app.models.base import ScanStatus
    from app.models.scan import Scan

    # Fresh engine for this asyncio.run() call — same reason as _run_pipeline.
    db_engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with session_factory() as session:
            result = await session.execute(select(Scan).where(Scan.id == scan_id))
            scan = result.scalar_one_or_none()
            if scan is not None:
                # Only update if not already in a terminal state
                if scan.status not in (ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED):
                    scan.status = ScanStatus.FAILED
                    scan.error_message = error_message[:2000]
                    scan.completed_at = datetime.now(timezone.utc)
                    await session.commit()
                    logger.info("Marked scan %d as FAILED via last-resort handler", scan_id)
                else:
                    logger.info(
                        "Scan %d already in terminal state (%s) — not overwriting",
                        scan_id,
                        scan.status.value,
                    )
    except Exception as exc:
        logger.error("_mark_scan_failed: could not update scan %d: %s", scan_id, exc)
    finally:
        await db_engine.dispose()
