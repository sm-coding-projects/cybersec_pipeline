"""Finding API endpoints.

Provides endpoints for listing, retrieving, updating, and exporting findings.
Supports filtering by scan, severity, tool, status, and free-text search.
All endpoints require JWT authentication.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database import get_db
from app.models.base import FindingStatus, Severity
from app.models.user import User
from app.schemas.finding import FindingListResponse, FindingResponse, FindingUpdate
from app.services import finding_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["findings"])


@router.get("/scans/{scan_id}/findings", response_model=FindingListResponse)
async def get_scan_findings(
    scan_id: int,
    severity: Severity | None = Query(default=None),
    source_tool: str | None = Query(default=None),
    finding_status: FindingStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FindingListResponse:
    """List findings for a specific scan with filtering and pagination."""
    findings, total = await finding_service.get_findings(
        db=db,
        scan_id=scan_id,
        severity=severity,
        source_tool=source_tool,
        status=finding_status,
        search=search,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return FindingListResponse(
        items=[FindingResponse.model_validate(f) for f in findings],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/findings/export")
async def export_findings(
    scan_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Export findings as a CSV file.

    If scan_id is provided, only findings for that scan are exported.
    Otherwise, all findings are included.
    """
    csv_content = await finding_service.export_findings_csv(db, scan_id)

    filename = f"findings_scan_{scan_id}.csv" if scan_id else "findings_all.csv"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/findings/{finding_id}", response_model=FindingResponse)
async def get_finding(
    finding_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FindingResponse:
    """Get a single finding by ID."""
    finding = await finding_service.get_finding(db, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    return FindingResponse.model_validate(finding)


@router.get("/findings", response_model=FindingListResponse)
async def list_all_findings(
    severity: Severity | None = Query(default=None),
    source_tool: str | None = Query(default=None),
    finding_status: FindingStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FindingListResponse:
    """List all findings across scans with filtering and pagination."""
    findings, total = await finding_service.get_findings(
        db=db,
        severity=severity,
        source_tool=source_tool,
        status=finding_status,
        search=search,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return FindingListResponse(
        items=[FindingResponse.model_validate(f) for f in findings],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.patch("/findings/{finding_id}", response_model=FindingResponse)
async def update_finding(
    finding_id: int,
    payload: FindingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FindingResponse:
    """Update a finding's status or duplicate flag.

    Use this to mark findings as confirmed, false positive, or resolved.
    """
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields to update",
        )

    finding = await finding_service.update_finding(db, finding_id, update_data)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    return FindingResponse.model_validate(finding)
