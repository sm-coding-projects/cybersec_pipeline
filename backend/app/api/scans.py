"""Scan CRUD API endpoints.

Provides endpoints for creating, listing, retrieving, cancelling, deleting,
retrying, and exporting scans.  All endpoints require JWT authentication.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import zipfile

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import get_current_user
from app.database import get_db
from app.models.base import ScanStatus
from app.models.user import User
from app.schemas.scan import ScanCreate, ScanListResponse, ScanLogResponse, ScanResponse
from app.services import finding_service, scan_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scans", tags=["scans"])


async def _get_redis() -> aioredis.Redis:
    """Create an async Redis client from settings."""
    return aioredis.from_url(settings.redis_url, decode_responses=True)


@router.post("", response_model=ScanResponse, status_code=status.HTTP_201_CREATED)
async def create_scan(
    payload: ScanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScanResponse:
    """Create and launch a new scan.

    Creates the scan record with 4 phase records and dispatches a Celery task
    for asynchronous pipeline execution.
    """
    scan = await scan_service.create_scan(
        db=db,
        target_domain=payload.target_domain,
        config=payload.config.model_dump(),
        user_id=current_user.id,
    )
    return ScanResponse.model_validate(scan)


@router.get("", response_model=ScanListResponse)
async def list_scans(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status_filter: ScanStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScanListResponse:
    """List all scans with pagination and optional status filter."""
    scans, total = await scan_service.list_scans(
        db=db,
        page=page,
        per_page=per_page,
        status_filter=status_filter,
    )
    return ScanListResponse(
        items=[ScanResponse.model_validate(s) for s in scans],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(
    scan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScanResponse:
    """Get scan details including phase statuses."""
    scan = await scan_service.get_scan(db, scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    return ScanResponse.model_validate(scan)


@router.delete("/{scan_id}")
async def delete_scan(
    scan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Cancel a running scan or delete a completed one.

    If the scan is running or pending, it will be cancelled first.
    Then the scan record is deleted.
    """
    scan = await scan_service.get_scan(db, scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    # Cancel if still active
    if scan.status in (ScanStatus.PENDING, ScanStatus.RUNNING):
        redis_client = await _get_redis()
        try:
            await scan_service.cancel_scan(db, redis_client, scan_id)
        finally:
            await redis_client.aclose()

    deleted = await scan_service.delete_scan(db, scan_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{scan_id}/retry", response_model=ScanResponse)
async def retry_scan(
    scan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScanResponse:
    """Retry a failed scan from the beginning.

    Only scans with status 'failed' can be retried.
    """
    scan = await scan_service.retry_scan(db, scan_id)
    if scan is None:
        existing = await scan_service.get_scan(db, scan_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Scan cannot be retried (current status: {existing.status.value})",
        )
    return ScanResponse.model_validate(scan)


@router.get("/{scan_id}/logs", response_model=ScanLogResponse)
async def get_scan_logs(
    scan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScanLogResponse:
    """Get aggregated log output for all phases of a scan."""
    scan = await scan_service.get_scan(db, scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    logs = await scan_service.get_scan_logs(db, scan_id)
    return ScanLogResponse(scan_id=scan_id, logs=logs)


@router.get("/{scan_id}/export")
async def export_scan(
    scan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Export full scan results as a ZIP archive.

    The archive contains:
    - findings.csv — all findings for the scan
    - targets.csv — all discovered targets
    - scan_summary.json — scan metadata and phase statuses
    """
    scan = await scan_service.get_scan(db, scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Findings CSV
        findings_csv = await finding_service.export_findings_csv(db, scan_id)
        zf.writestr("findings.csv", findings_csv)

        # 2. Targets CSV
        targets_csv = _build_targets_csv(scan)
        zf.writestr("targets.csv", targets_csv)

        # 3. Scan summary JSON
        summary = _build_scan_summary(scan)
        zf.writestr("scan_summary.json", json.dumps(summary, indent=2, default=str))

    zip_buffer.seek(0)

    filename = f"scan_{scan.scan_uid}_export.zip"
    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_targets_csv(scan: "Scan") -> str:
    """Build a CSV string of all targets for a scan."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID",
        "Type",
        "Value",
        "Source Tool",
        "Is Live",
        "Resolved IPs",
        "Open Ports",
        "HTTP Status",
        "HTTP Title",
        "Technologies",
        "Created At",
    ])

    for target in scan.targets:
        writer.writerow([
            target.id,
            target.target_type.value if target.target_type else "",
            target.value,
            target.source_tool,
            target.is_live,
            json.dumps(target.resolved_ips) if target.resolved_ips else "",
            json.dumps(target.open_ports) if target.open_ports else "",
            target.http_status or "",
            target.http_title or "",
            json.dumps(target.technologies) if target.technologies else "",
            target.created_at.isoformat() if target.created_at else "",
        ])

    return output.getvalue()


def _build_scan_summary(scan: "Scan") -> dict:
    """Build a summary dict for the scan, suitable for JSON serialization."""
    return {
        "scan_id": scan.id,
        "scan_uid": scan.scan_uid,
        "target_domain": scan.target_domain,
        "status": scan.status.value,
        "current_phase": scan.current_phase,
        "config": scan.config,
        "results_dir": scan.results_dir,
        "started_at": scan.started_at,
        "completed_at": scan.completed_at,
        "error_message": scan.error_message,
        "created_at": scan.created_at,
        "total_targets": len(scan.targets),
        "total_findings": len(scan.findings),
        "phases": [
            {
                "phase_number": phase.phase_number,
                "phase_name": phase.phase_name,
                "status": phase.status.value,
                "tool_statuses": phase.tool_statuses,
                "started_at": phase.started_at,
                "completed_at": phase.completed_at,
                "duration_seconds": phase.duration_seconds,
                "error_message": phase.error_message,
            }
            for phase in scan.phases
        ],
    }
