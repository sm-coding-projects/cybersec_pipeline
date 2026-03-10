"""Finding operations service.

Handles retrieval, filtering, aggregation, and export of findings.
Provides dashboard statistics and severity breakdowns.
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import FindingStatus, ScanStatus, Severity, TargetType
from app.models.finding import Finding
from app.models.scan import Scan
from app.models.target import Target

logger = logging.getLogger(__name__)


async def get_findings(
    db: AsyncSession,
    scan_id: int | None = None,
    severity: Severity | None = None,
    source_tool: str | None = None,
    status: FindingStatus | None = None,
    search: str | None = None,
    page: int = 1,
    per_page: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[Finding], int]:
    """Return a paginated, filterable list of findings and the total count.

    Supports filtering by scan_id, severity, source_tool, status, and free-text
    search on the title field.  Results can be sorted by any column.
    """
    query = select(Finding)
    count_query = select(func.count()).select_from(Finding)

    # Apply filters
    filters = []
    if scan_id is not None:
        filters.append(Finding.scan_id == scan_id)
    if severity is not None:
        filters.append(Finding.severity == severity)
    if source_tool is not None:
        filters.append(Finding.source_tool == source_tool)
    if status is not None:
        filters.append(Finding.status == status)
    if search:
        filters.append(Finding.title.ilike(f"%{search}%"))

    for f in filters:
        query = query.where(f)
        count_query = count_query.where(f)

    # Total count
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Sorting
    sort_column = getattr(Finding, sort_by, Finding.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # Pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    findings = list(result.scalars().all())

    return findings, total


async def get_finding(db: AsyncSession, finding_id: int) -> Finding | None:
    """Return a single finding by ID, or None if not found."""
    return await db.get(Finding, finding_id)


async def update_finding(
    db: AsyncSession,
    finding_id: int,
    update_data: dict[str, Any],
) -> Finding | None:
    """Update a finding's status or is_duplicate flag.

    Only the fields present in update_data are modified.
    Returns the updated finding, or None if not found.
    """
    finding = await db.get(Finding, finding_id)
    if finding is None:
        return None

    if "status" in update_data and update_data["status"] is not None:
        finding.status = update_data["status"]
    if "is_duplicate" in update_data and update_data["is_duplicate"] is not None:
        finding.is_duplicate = update_data["is_duplicate"]

    await db.commit()
    await db.refresh(finding)
    return finding


async def get_dashboard_stats(db: AsyncSession) -> dict[str, int]:
    """Compute aggregate dashboard statistics.

    Returns counts for scans, findings by severity, targets, and unique assets.
    """
    # Scan counts
    total_scans_result = await db.execute(select(func.count()).select_from(Scan))
    total_scans = total_scans_result.scalar_one()

    active_scans_result = await db.execute(
        select(func.count())
        .select_from(Scan)
        .where(Scan.status.in_([ScanStatus.PENDING, ScanStatus.RUNNING]))
    )
    active_scans = active_scans_result.scalar_one()

    # Finding counts by severity
    severity_counts = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Finding.severity == Severity.CRITICAL).label("critical"),
            func.count().filter(Finding.severity == Severity.HIGH).label("high"),
            func.count().filter(Finding.severity == Severity.MEDIUM).label("medium"),
            func.count().filter(Finding.severity == Severity.LOW).label("low"),
            func.count().filter(Finding.severity == Severity.INFO).label("info"),
        ).select_from(Finding)
    )
    row = severity_counts.one()

    # Target counts
    total_targets_result = await db.execute(select(func.count()).select_from(Target))
    total_targets = total_targets_result.scalar_one()

    unique_ips_result = await db.execute(
        select(func.count(distinct(Target.value)))
        .select_from(Target)
        .where(Target.target_type == TargetType.IP)
    )
    unique_ips = unique_ips_result.scalar_one()

    unique_subdomains_result = await db.execute(
        select(func.count(distinct(Target.value)))
        .select_from(Target)
        .where(Target.target_type == TargetType.SUBDOMAIN)
    )
    unique_subdomains = unique_subdomains_result.scalar_one()

    return {
        "total_scans": total_scans,
        "active_scans": active_scans,
        "total_findings": row.total,
        "critical_findings": row.critical,
        "high_findings": row.high,
        "medium_findings": row.medium,
        "low_findings": row.low,
        "info_findings": row.info,
        "total_targets_discovered": total_targets,
        "unique_ips": unique_ips,
        "unique_subdomains": unique_subdomains,
    }


async def get_severity_breakdown(db: AsyncSession) -> list[dict[str, Any]]:
    """Return finding counts grouped by severity, suitable for chart data."""
    result = await db.execute(
        select(
            Finding.severity,
            func.count().label("count"),
        )
        .select_from(Finding)
        .group_by(Finding.severity)
        .order_by(
            case(
                (Finding.severity == Severity.CRITICAL, 1),
                (Finding.severity == Severity.HIGH, 2),
                (Finding.severity == Severity.MEDIUM, 3),
                (Finding.severity == Severity.LOW, 4),
                (Finding.severity == Severity.INFO, 5),
                else_=6,
            )
        )
    )

    return [
        {"severity": row.severity.value, "count": row.count}
        for row in result.all()
    ]


async def get_scan_timeline(db: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    """Return the most recent scans for the timeline display."""
    result = await db.execute(
        select(Scan)
        .order_by(Scan.created_at.desc())
        .limit(limit)
    )

    return [
        {
            "id": scan.id,
            "scan_uid": scan.scan_uid,
            "target_domain": scan.target_domain,
            "status": scan.status.value,
            "created_at": scan.created_at,
            "completed_at": scan.completed_at,
        }
        for scan in result.scalars().all()
    ]


async def get_top_findings(db: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    """Return the most common finding types (grouped by title and severity)."""
    result = await db.execute(
        select(
            Finding.title,
            Finding.severity,
            func.count().label("count"),
        )
        .select_from(Finding)
        .group_by(Finding.title, Finding.severity)
        .order_by(func.count().desc())
        .limit(limit)
    )

    return [
        {
            "title": row.title,
            "count": row.count,
            "severity": row.severity.value,
        }
        for row in result.all()
    ]


async def export_findings_csv(db: AsyncSession, scan_id: int | None = None) -> str:
    """Generate a CSV export of findings.

    If scan_id is provided, only findings for that scan are included.
    Returns the CSV content as a string.
    """
    query = select(Finding).order_by(Finding.severity, Finding.created_at.desc())
    if scan_id is not None:
        query = query.where(Finding.scan_id == scan_id)

    result = await db.execute(query)
    findings = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "ID",
        "Scan ID",
        "Title",
        "Severity",
        "Source Tool",
        "Status",
        "Affected Host",
        "Affected URL",
        "Affected Port",
        "Description",
        "Remediation",
        "Template ID",
        "Is Duplicate",
        "Created At",
    ])

    for finding in findings:
        writer.writerow([
            finding.id,
            finding.scan_id,
            finding.title,
            finding.severity.value,
            finding.source_tool,
            finding.status.value,
            finding.affected_host or "",
            finding.affected_url or "",
            finding.affected_port or "",
            finding.description or "",
            finding.remediation or "",
            finding.template_id or "",
            finding.is_duplicate,
            finding.created_at.isoformat() if finding.created_at else "",
        ])

    return output.getvalue()
