"""Tests for finding API endpoints including listing, filtering, update, and CSV export."""

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
async def scan_with_findings(db_session: AsyncSession, test_user: User) -> Scan:
    """Create a scan with multiple findings of varying severity for filter testing."""
    scan = Scan(
        scan_uid="scan_findings_001",
        target_domain="testsite.com",
        status=ScanStatus.COMPLETED,
        current_phase=4,
        config={},
        results_dir="/results/scan_findings_001/",
        created_by=test_user.id,
    )
    db_session.add(scan)
    await db_session.flush()

    # Phases
    for i, name in enumerate(["recon", "network", "vulnscan", "report"], start=1):
        phase = ScanPhase(
            scan_id=scan.id,
            phase_number=i,
            phase_name=name,
            status=PhaseStatus.COMPLETED,
            tool_statuses={},
        )
        db_session.add(phase)

    # Findings with different severities and tools
    findings_data = [
        ("SQL Injection", Severity.CRITICAL, "nuclei", FindingStatus.OPEN, "testsite.com"),
        ("XSS Reflected", Severity.HIGH, "zap", FindingStatus.OPEN, "testsite.com"),
        ("Missing HSTS", Severity.MEDIUM, "nuclei", FindingStatus.CONFIRMED, "testsite.com"),
        ("Server Header", Severity.LOW, "zap", FindingStatus.FALSE_POSITIVE, "testsite.com"),
        ("HTTP/2 Support", Severity.INFO, "httpx", FindingStatus.OPEN, "testsite.com"),
    ]

    for title, severity, tool, fstatus, host in findings_data:
        finding = Finding(
            scan_id=scan.id,
            title=title,
            severity=severity,
            source_tool=tool,
            description=f"Description for {title}",
            affected_host=host,
            status=fstatus,
            reference_urls=[],
        )
        db_session.add(finding)

    await db_session.commit()
    await db_session.refresh(scan)
    return scan


# ── List Findings ──


@pytest.mark.asyncio
async def test_list_scan_findings(
    client: AsyncClient, auth_headers: dict, scan_with_findings: Scan
) -> None:
    """Listing findings for a scan returns all findings."""
    response = await client.get(
        f"/api/v1/scans/{scan_with_findings.id}/findings", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 5


@pytest.mark.asyncio
async def test_list_all_findings(
    client: AsyncClient, auth_headers: dict, scan_with_findings: Scan
) -> None:
    """Listing all findings across scans works."""
    response = await client.get("/api/v1/findings", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 5


@pytest.mark.asyncio
async def test_list_findings_empty_scan(client: AsyncClient, auth_headers: dict) -> None:
    """Listing findings for a scan that doesn't exist returns 200 with empty list."""
    # Note: the endpoint filters by scan_id but doesn't verify scan existence,
    # so it returns an empty result set rather than 404.
    response = await client.get("/api/v1/scans/99999/findings", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


# ── Filter by Severity ──


@pytest.mark.asyncio
async def test_filter_findings_by_severity(
    client: AsyncClient, auth_headers: dict, scan_with_findings: Scan
) -> None:
    """Filtering findings by severity returns only matching results."""
    response = await client.get(
        f"/api/v1/scans/{scan_with_findings.id}/findings",
        params={"severity": "critical"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["severity"] == "critical"
    assert data["items"][0]["title"] == "SQL Injection"


# ── Filter by Source Tool ──


@pytest.mark.asyncio
async def test_filter_findings_by_tool(
    client: AsyncClient, auth_headers: dict, scan_with_findings: Scan
) -> None:
    """Filtering findings by source_tool returns only matching results."""
    response = await client.get(
        f"/api/v1/scans/{scan_with_findings.id}/findings",
        params={"source_tool": "nuclei"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    for item in data["items"]:
        assert item["source_tool"] == "nuclei"


# ── Filter by Status ──


@pytest.mark.asyncio
async def test_filter_findings_by_status(
    client: AsyncClient, auth_headers: dict, scan_with_findings: Scan
) -> None:
    """Filtering findings by status returns only matching results."""
    response = await client.get(
        f"/api/v1/scans/{scan_with_findings.id}/findings",
        params={"status": "confirmed"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "confirmed"


# ── Search ──


@pytest.mark.asyncio
async def test_search_findings(
    client: AsyncClient, auth_headers: dict, scan_with_findings: Scan
) -> None:
    """Free-text search on title returns matching findings."""
    response = await client.get(
        f"/api/v1/scans/{scan_with_findings.id}/findings",
        params={"search": "SQL"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert "SQL" in data["items"][0]["title"]


# ── Pagination ──


@pytest.mark.asyncio
async def test_findings_pagination(
    client: AsyncClient, auth_headers: dict, scan_with_findings: Scan
) -> None:
    """Pagination correctly limits results and reports total."""
    response = await client.get(
        f"/api/v1/scans/{scan_with_findings.id}/findings",
        params={"page": 1, "per_page": 2},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["per_page"] == 2


# ── Get Single Finding ──


@pytest.mark.asyncio
async def test_get_finding(
    client: AsyncClient, auth_headers: dict, scan_with_findings: Scan
) -> None:
    """Getting a single finding by ID returns full details."""
    # First get the list to get a finding ID
    list_response = await client.get(
        f"/api/v1/scans/{scan_with_findings.id}/findings", headers=auth_headers
    )
    finding_id = list_response.json()["items"][0]["id"]

    response = await client.get(f"/api/v1/findings/{finding_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == finding_id
    assert "title" in data
    assert "severity" in data


@pytest.mark.asyncio
async def test_get_finding_not_found(client: AsyncClient, auth_headers: dict) -> None:
    """Getting a nonexistent finding returns 404."""
    response = await client.get("/api/v1/findings/99999", headers=auth_headers)
    assert response.status_code == 404


# ── Update Finding ──


@pytest.mark.asyncio
async def test_update_finding_status(
    client: AsyncClient, auth_headers: dict, scan_with_findings: Scan
) -> None:
    """Updating a finding's status works correctly."""
    list_response = await client.get(
        f"/api/v1/scans/{scan_with_findings.id}/findings", headers=auth_headers
    )
    finding_id = list_response.json()["items"][0]["id"]

    response = await client.patch(
        f"/api/v1/findings/{finding_id}",
        json={"status": "resolved"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "resolved"


@pytest.mark.asyncio
async def test_update_finding_duplicate_flag(
    client: AsyncClient, auth_headers: dict, scan_with_findings: Scan
) -> None:
    """Updating a finding's is_duplicate flag works correctly."""
    list_response = await client.get(
        f"/api/v1/scans/{scan_with_findings.id}/findings", headers=auth_headers
    )
    finding_id = list_response.json()["items"][0]["id"]

    response = await client.patch(
        f"/api/v1/findings/{finding_id}",
        json={"is_duplicate": True},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["is_duplicate"] is True


@pytest.mark.asyncio
async def test_update_finding_empty_payload(
    client: AsyncClient, auth_headers: dict, scan_with_findings: Scan
) -> None:
    """Updating a finding with no fields returns 422."""
    list_response = await client.get(
        f"/api/v1/scans/{scan_with_findings.id}/findings", headers=auth_headers
    )
    finding_id = list_response.json()["items"][0]["id"]

    response = await client.patch(
        f"/api/v1/findings/{finding_id}",
        json={},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_finding_not_found(client: AsyncClient, auth_headers: dict) -> None:
    """Updating a nonexistent finding returns 404."""
    response = await client.patch(
        "/api/v1/findings/99999",
        json={"status": "resolved"},
        headers=auth_headers,
    )
    assert response.status_code == 404


# ── CSV Export ──


@pytest.mark.asyncio
async def test_export_findings_csv(
    client: AsyncClient, auth_headers: dict, scan_with_findings: Scan
) -> None:
    """CSV export returns proper CSV with all findings."""
    response = await client.get(
        "/api/v1/findings/export",
        params={"scan_id": scan_with_findings.id},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "content-disposition" in response.headers
    assert f"scan_{scan_with_findings.id}" in response.headers["content-disposition"]

    csv_text = response.text
    lines = csv_text.strip().split("\n")
    # Header + 5 data rows
    assert len(lines) == 6
    header = lines[0]
    assert "ID" in header
    assert "Title" in header
    assert "Severity" in header
    assert "Source Tool" in header
    assert "Status" in header
    assert "Description" in header
    assert "Created At" in header


@pytest.mark.asyncio
async def test_export_findings_csv_all(
    client: AsyncClient, auth_headers: dict, scan_with_findings: Scan
) -> None:
    """CSV export without scan_id returns all findings."""
    response = await client.get("/api/v1/findings/export", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "findings_all.csv" in response.headers["content-disposition"]

    csv_text = response.text
    lines = csv_text.strip().split("\n")
    assert len(lines) >= 6  # header + at least 5 findings


@pytest.mark.asyncio
async def test_export_findings_csv_empty(client: AsyncClient, auth_headers: dict) -> None:
    """CSV export for a scan with no findings returns header-only CSV."""
    response = await client.get(
        "/api/v1/findings/export",
        params={"scan_id": 99999},
        headers=auth_headers,
    )
    assert response.status_code == 200
    csv_text = response.text
    lines = csv_text.strip().split("\n")
    # Only header row
    assert len(lines) == 1
    assert "ID" in lines[0]
