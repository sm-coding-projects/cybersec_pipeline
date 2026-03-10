"""Tests for dashboard statistics API endpoints."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import FindingStatus, PhaseStatus, ScanStatus, Severity, TargetType
from app.models.finding import Finding
from app.models.scan import Scan, ScanPhase
from app.models.target import Target
from app.models.user import User


@pytest_asyncio.fixture
async def dashboard_data(db_session: AsyncSession, test_user: User) -> None:
    """Populate the database with scans, findings, and targets for dashboard tests."""
    # Create two scans: one completed, one running
    scan1 = Scan(
        scan_uid="scan_dash_001",
        target_domain="alpha.com",
        status=ScanStatus.COMPLETED,
        current_phase=4,
        config={},
        results_dir="/results/scan_dash_001/",
        created_by=test_user.id,
    )
    scan2 = Scan(
        scan_uid="scan_dash_002",
        target_domain="beta.com",
        status=ScanStatus.RUNNING,
        current_phase=2,
        config={},
        results_dir="/results/scan_dash_002/",
        created_by=test_user.id,
    )
    db_session.add_all([scan1, scan2])
    await db_session.flush()

    # Phases for scan1
    for i, name in enumerate(["recon", "network", "vulnscan", "report"], start=1):
        db_session.add(ScanPhase(
            scan_id=scan1.id,
            phase_number=i,
            phase_name=name,
            status=PhaseStatus.COMPLETED,
            tool_statuses={},
        ))

    # Phases for scan2
    for i, name in enumerate(["recon", "network", "vulnscan", "report"], start=1):
        s = PhaseStatus.COMPLETED if i <= 2 else PhaseStatus.PENDING
        db_session.add(ScanPhase(
            scan_id=scan2.id,
            phase_number=i,
            phase_name=name,
            status=s,
            tool_statuses={},
        ))

    # Targets
    t1 = Target(
        scan_id=scan1.id,
        target_type=TargetType.IP,
        value="1.2.3.4",
        source_tool="dnsx",
        is_live=True,
    )
    t2 = Target(
        scan_id=scan1.id,
        target_type=TargetType.SUBDOMAIN,
        value="www.alpha.com",
        source_tool="theharvester",
        is_live=True,
    )
    t3 = Target(
        scan_id=scan2.id,
        target_type=TargetType.SUBDOMAIN,
        value="api.beta.com",
        source_tool="amass",
        is_live=False,
    )
    db_session.add_all([t1, t2, t3])

    # Findings with different severities
    findings_data = [
        (scan1.id, "Critical Bug", Severity.CRITICAL, "nuclei"),
        (scan1.id, "High Issue", Severity.HIGH, "zap"),
        (scan1.id, "Medium Warning", Severity.MEDIUM, "nuclei"),
        (scan1.id, "Low Notice", Severity.LOW, "httpx"),
        (scan1.id, "Info Note", Severity.INFO, "httpx"),
    ]
    for scan_id, title, severity, tool in findings_data:
        db_session.add(Finding(
            scan_id=scan_id,
            title=title,
            severity=severity,
            source_tool=tool,
            description=f"Desc: {title}",
            status=FindingStatus.OPEN,
            reference_urls=[],
        ))

    await db_session.commit()


# ── Dashboard Stats ──


@pytest.mark.asyncio
async def test_dashboard_stats(
    client: AsyncClient, auth_headers: dict, dashboard_data: None
) -> None:
    """Dashboard stats returns correct aggregate counts."""
    response = await client.get("/api/v1/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    assert data["total_scans"] == 2
    assert data["active_scans"] == 1  # one running
    assert data["total_findings"] == 5
    assert data["critical_findings"] == 1
    assert data["high_findings"] == 1
    assert data["medium_findings"] == 1
    assert data["low_findings"] == 1
    assert data["info_findings"] == 1
    assert data["total_targets_discovered"] == 3
    assert data["unique_ips"] == 1
    assert data["unique_subdomains"] == 2


@pytest.mark.asyncio
async def test_dashboard_stats_empty(client: AsyncClient, auth_headers: dict) -> None:
    """Dashboard stats with no data returns all zeros."""
    response = await client.get("/api/v1/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_scans"] == 0
    assert data["total_findings"] == 0
    assert data["active_scans"] == 0


@pytest.mark.asyncio
async def test_dashboard_stats_unauthenticated(client: AsyncClient) -> None:
    """Dashboard stats without auth returns 401/403."""
    response = await client.get("/api/v1/dashboard/stats")
    assert response.status_code in (401, 403)


# ── Severity Breakdown ──


@pytest.mark.asyncio
async def test_severity_breakdown(
    client: AsyncClient, auth_headers: dict, dashboard_data: None
) -> None:
    """Severity breakdown returns counts grouped by severity."""
    response = await client.get("/api/v1/dashboard/severity-breakdown", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data

    severity_map = {item["severity"]: item["count"] for item in data["items"]}
    assert severity_map.get("critical", 0) == 1
    assert severity_map.get("high", 0) == 1
    assert severity_map.get("medium", 0) == 1


@pytest.mark.asyncio
async def test_severity_breakdown_empty(client: AsyncClient, auth_headers: dict) -> None:
    """Severity breakdown with no findings returns empty items list."""
    response = await client.get("/api/v1/dashboard/severity-breakdown", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


# ── Scan Timeline ──


@pytest.mark.asyncio
async def test_scan_timeline(
    client: AsyncClient, auth_headers: dict, dashboard_data: None
) -> None:
    """Scan timeline returns recent scans in order."""
    response = await client.get("/api/v1/dashboard/scan-timeline", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_scan_timeline_limit(
    client: AsyncClient, auth_headers: dict, dashboard_data: None
) -> None:
    """Scan timeline respects the limit parameter."""
    response = await client.get(
        "/api/v1/dashboard/scan-timeline", params={"limit": 1}, headers=auth_headers
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


# ── Top Findings ──


@pytest.mark.asyncio
async def test_top_findings(
    client: AsyncClient, auth_headers: dict, dashboard_data: None
) -> None:
    """Top findings returns finding types grouped by title and severity."""
    response = await client.get("/api/v1/dashboard/top-findings", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 5
    # Each item should have title, count, severity
    for item in data["items"]:
        assert "title" in item
        assert "count" in item
        assert "severity" in item


@pytest.mark.asyncio
async def test_top_findings_empty(client: AsyncClient, auth_headers: dict) -> None:
    """Top findings with no data returns empty items list."""
    response = await client.get("/api/v1/dashboard/top-findings", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["items"] == []
