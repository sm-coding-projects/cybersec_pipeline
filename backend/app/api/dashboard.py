"""Dashboard API endpoints.

Provides aggregate statistics, severity breakdowns, scan timeline,
and top findings for the frontend dashboard.
All endpoints require JWT authentication.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.finding import (
    DashboardStatsResponse,
    ScanTimelineResponse,
    SeverityBreakdownResponse,
    TopFindingsResponse,
)
from app.services import finding_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardStatsResponse:
    """Get aggregate dashboard statistics.

    Returns total scan count, active scans, findings by severity,
    target counts, and unique asset counts.
    """
    stats = await finding_service.get_dashboard_stats(db)
    return DashboardStatsResponse(**stats)


@router.get("/severity-breakdown", response_model=SeverityBreakdownResponse)
async def get_severity_breakdown(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SeverityBreakdownResponse:
    """Get findings count grouped by severity for chart rendering."""
    items = await finding_service.get_severity_breakdown(db)
    return SeverityBreakdownResponse(items=items)


@router.get("/scan-timeline", response_model=ScanTimelineResponse)
async def get_scan_timeline(
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScanTimelineResponse:
    """Get recent scan history for timeline display."""
    items = await finding_service.get_scan_timeline(db, limit=limit)
    return ScanTimelineResponse(items=items)


@router.get("/top-findings", response_model=TopFindingsResponse)
async def get_top_findings(
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TopFindingsResponse:
    """Get the most common finding types across all scans."""
    items = await finding_service.get_top_findings(db, limit=limit)
    return TopFindingsResponse(items=items)
