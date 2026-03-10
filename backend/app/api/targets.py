"""Target API endpoints.

Provides endpoints for listing discovered targets and target statistics
for a specific scan.  All endpoints require JWT authentication.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database import get_db
from app.models.base import TargetType
from app.models.scan import Scan
from app.models.target import Target
from app.models.user import User
from app.schemas.target import TargetListResponse, TargetResponse, TargetStatsResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["targets"])


@router.get("/scans/{scan_id}/targets", response_model=TargetListResponse)
async def list_targets(
    scan_id: int,
    target_type: TargetType | None = Query(default=None, alias="type"),
    is_live: bool | None = Query(default=None),
    source_tool: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TargetListResponse:
    """List discovered targets for a specific scan.

    Supports filtering by target type, liveness, and source tool.
    """
    # Verify scan exists
    scan = await db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    query = select(Target).where(Target.scan_id == scan_id)
    count_query = select(func.count()).select_from(Target).where(Target.scan_id == scan_id)

    # Apply filters
    if target_type is not None:
        query = query.where(Target.target_type == target_type)
        count_query = count_query.where(Target.target_type == target_type)
    if is_live is not None:
        query = query.where(Target.is_live == is_live)
        count_query = count_query.where(Target.is_live == is_live)
    if source_tool is not None:
        query = query.where(Target.source_tool == source_tool)
        count_query = count_query.where(Target.source_tool == source_tool)

    # Total count
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Paginate
    offset = (page - 1) * per_page
    query = query.order_by(Target.created_at.desc()).offset(offset).limit(per_page)

    result = await db.execute(query)
    targets = list(result.scalars().all())

    return TargetListResponse(
        items=[TargetResponse.model_validate(t) for t in targets],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/scans/{scan_id}/targets/stats", response_model=TargetStatsResponse)
async def get_target_stats(
    scan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TargetStatsResponse:
    """Get target counts by type for a specific scan."""
    # Verify scan exists
    scan = await db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    # Total count
    total_result = await db.execute(
        select(func.count()).select_from(Target).where(Target.scan_id == scan_id)
    )
    total = total_result.scalar_one()

    # Count by type
    subdomains_result = await db.execute(
        select(func.count())
        .select_from(Target)
        .where(Target.scan_id == scan_id, Target.target_type == TargetType.SUBDOMAIN)
    )
    subdomains = subdomains_result.scalar_one()

    ips_result = await db.execute(
        select(func.count())
        .select_from(Target)
        .where(Target.scan_id == scan_id, Target.target_type == TargetType.IP)
    )
    ips = ips_result.scalar_one()

    emails_result = await db.execute(
        select(func.count())
        .select_from(Target)
        .where(Target.scan_id == scan_id, Target.target_type == TargetType.EMAIL)
    )
    emails = emails_result.scalar_one()

    urls_result = await db.execute(
        select(func.count())
        .select_from(Target)
        .where(Target.scan_id == scan_id, Target.target_type == TargetType.URL)
    )
    urls = urls_result.scalar_one()

    # Live count
    live_result = await db.execute(
        select(func.count())
        .select_from(Target)
        .where(Target.scan_id == scan_id, Target.is_live == True)  # noqa: E712
    )
    live = live_result.scalar_one()

    return TargetStatsResponse(
        total=total,
        subdomains=subdomains,
        ips=ips,
        emails=emails,
        urls=urls,
        live=live,
    )
