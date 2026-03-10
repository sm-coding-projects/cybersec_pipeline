"""Tests for scan CRUD and export API endpoints."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from unittest.mock import AsyncMock, patch

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
async def sample_scan(db_session: AsyncSession, test_user: User) -> Scan:
    """Create a completed scan with phases, targets, and findings for testing."""
    scan = Scan(
        scan_uid="scan_test_001",
        target_domain="example.com",
        status=ScanStatus.COMPLETED,
        current_phase=4,
        config={"harvester_sources": "bing,crtsh"},
        results_dir="/results/scan_test_001/",
        created_by=test_user.id,
    )
    db_session.add(scan)
    await db_session.flush()

    # Create phases
    for i, name in enumerate(["recon", "network", "vulnscan", "report"], start=1):
        phase = ScanPhase(
            scan_id=scan.id,
            phase_number=i,
            phase_name=name,
            status=PhaseStatus.COMPLETED,
            tool_statuses={"tool1": "completed"},
        )
        db_session.add(phase)

    # Create a target
    target = Target(
        scan_id=scan.id,
        target_type=TargetType.SUBDOMAIN,
        value="sub.example.com",
        source_tool="theharvester",
        is_live=True,
    )
    db_session.add(target)
    await db_session.flush()

    # Create findings
    finding = Finding(
        scan_id=scan.id,
        target_id=target.id,
        title="Test XSS Vulnerability",
        severity=Severity.HIGH,
        source_tool="nuclei",
        description="A reflected XSS vulnerability was found.",
        affected_url="https://sub.example.com/search",
        affected_host="sub.example.com",
        affected_port=443,
        status=FindingStatus.OPEN,
        reference_urls=["https://owasp.org/xss"],
    )
    db_session.add(finding)

    finding2 = Finding(
        scan_id=scan.id,
        title="Information Disclosure",
        severity=Severity.INFO,
        source_tool="zap",
        description="Server version header exposed.",
        affected_host="example.com",
        status=FindingStatus.OPEN,
        reference_urls=[],
    )
    db_session.add(finding2)

    await db_session.commit()
    await db_session.refresh(scan)
    return scan


# ── Scan Creation ──


@pytest.mark.asyncio
async def test_create_scan(client: AsyncClient, auth_headers: dict) -> None:
    """Creating a scan returns 201 with the scan record."""
    with patch("app.services.scan_service.run_scan_task", create=True) as mock_task:
        # Mock the Celery task import inside scan_service
        with patch("app.tasks.scan_tasks.run_scan_task") as mock_celery:
            mock_celery.delay = AsyncMock()
            response = await client.post(
                "/api/v1/scans",
                json={"target_domain": "example.com"},
                headers=auth_headers,
            )

    assert response.status_code == 201
    data = response.json()
    assert data["target_domain"] == "example.com"
    assert data["status"] == "pending"
    assert data["current_phase"] == 0
    assert len(data["phases"]) == 4
    assert data["phases"][0]["phase_name"] == "recon"
    assert data["phases"][3]["phase_name"] == "report"


@pytest.mark.asyncio
async def test_create_scan_unauthenticated(client: AsyncClient) -> None:
    """Creating a scan without auth returns 401/403."""
    response = await client.post(
        "/api/v1/scans",
        json={"target_domain": "example.com"},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_scan_invalid_domain(client: AsyncClient, auth_headers: dict) -> None:
    """Creating a scan with an invalid domain returns 422."""
    response = await client.post(
        "/api/v1/scans",
        json={"target_domain": "ab"},  # too short (min_length=3)
        headers=auth_headers,
    )
    assert response.status_code == 422


# ── Scan Retrieval ──


@pytest.mark.asyncio
async def test_list_scans(client: AsyncClient, auth_headers: dict, sample_scan: Scan) -> None:
    """Listing scans returns paginated results."""
    response = await client.get("/api/v1/scans", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["page"] == 1
    assert data["per_page"] == 20
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_list_scans_filter_by_status(
    client: AsyncClient, auth_headers: dict, sample_scan: Scan
) -> None:
    """Listing scans with status filter returns only matching scans."""
    response = await client.get(
        "/api/v1/scans", params={"status": "completed"}, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["status"] == "completed"


@pytest.mark.asyncio
async def test_list_scans_filter_no_results(client: AsyncClient, auth_headers: dict) -> None:
    """Listing scans with a status that has no matches returns empty list."""
    response = await client.get(
        "/api/v1/scans", params={"status": "cancelled"}, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_get_scan(client: AsyncClient, auth_headers: dict, sample_scan: Scan) -> None:
    """Getting a single scan returns its full details."""
    response = await client.get(f"/api/v1/scans/{sample_scan.id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_scan.id
    assert data["target_domain"] == "example.com"
    assert data["status"] == "completed"
    assert len(data["phases"]) == 4


@pytest.mark.asyncio
async def test_get_scan_not_found(client: AsyncClient, auth_headers: dict) -> None:
    """Getting a nonexistent scan returns 404."""
    response = await client.get("/api/v1/scans/99999", headers=auth_headers)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ── Scan Lifecycle ──


@pytest.mark.asyncio
async def test_delete_scan(client: AsyncClient, auth_headers: dict, sample_scan: Scan) -> None:
    """Deleting a scan returns 204 and removes it."""
    response = await client.delete(f"/api/v1/scans/{sample_scan.id}", headers=auth_headers)
    assert response.status_code == 204

    # Verify it's gone
    get_response = await client.get(f"/api/v1/scans/{sample_scan.id}", headers=auth_headers)
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_scan_not_found(client: AsyncClient, auth_headers: dict) -> None:
    """Deleting a nonexistent scan returns 404."""
    response = await client.delete("/api/v1/scans/99999", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_retry_scan_not_failed(
    client: AsyncClient, auth_headers: dict, sample_scan: Scan
) -> None:
    """Retrying a completed scan returns 409 Conflict."""
    response = await client.post(
        f"/api/v1/scans/{sample_scan.id}/retry", headers=auth_headers
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_retry_scan_not_found(client: AsyncClient, auth_headers: dict) -> None:
    """Retrying a nonexistent scan returns 404."""
    response = await client.post("/api/v1/scans/99999/retry", headers=auth_headers)
    assert response.status_code == 404


# ── Scan Logs ──


@pytest.mark.asyncio
async def test_get_scan_logs(client: AsyncClient, auth_headers: dict, sample_scan: Scan) -> None:
    """Getting scan logs returns structured phase log data."""
    response = await client.get(
        f"/api/v1/scans/{sample_scan.id}/logs", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["scan_id"] == sample_scan.id
    assert len(data["logs"]) == 4
    assert data["logs"][0]["phase_name"] == "recon"


@pytest.mark.asyncio
async def test_get_scan_logs_not_found(client: AsyncClient, auth_headers: dict) -> None:
    """Getting logs for nonexistent scan returns 404."""
    response = await client.get("/api/v1/scans/99999/logs", headers=auth_headers)
    assert response.status_code == 404


# ── ZIP Export ──


@pytest.mark.asyncio
async def test_export_scan_zip(client: AsyncClient, auth_headers: dict, sample_scan: Scan) -> None:
    """Exporting a scan returns a ZIP with findings CSV, targets CSV, and summary JSON."""
    response = await client.get(
        f"/api/v1/scans/{sample_scan.id}/export", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "content-disposition" in response.headers
    assert "scan_test_001" in response.headers["content-disposition"]

    # Verify the ZIP contents
    zip_data = BytesIO(response.content)
    with zipfile.ZipFile(zip_data, "r") as zf:
        names = zf.namelist()
        assert "findings.csv" in names
        assert "targets.csv" in names
        assert "scan_summary.json" in names

        # Verify findings CSV
        findings_csv = zf.read("findings.csv").decode("utf-8")
        assert "ID" in findings_csv
        assert "Test XSS Vulnerability" in findings_csv
        assert "Information Disclosure" in findings_csv

        # Verify targets CSV
        targets_csv = zf.read("targets.csv").decode("utf-8")
        assert "sub.example.com" in targets_csv

        # Verify scan summary JSON is valid
        summary = json.loads(zf.read("scan_summary.json").decode("utf-8"))
        assert summary["scan_uid"] == "scan_test_001"
        assert summary["target_domain"] == "example.com"
        assert summary["status"] == "completed"
        assert len(summary["phases"]) == 4
        assert summary["total_findings"] == 2
        assert summary["total_targets"] == 1


@pytest.mark.asyncio
async def test_export_scan_not_found(client: AsyncClient, auth_headers: dict) -> None:
    """Exporting a nonexistent scan returns 404."""
    response = await client.get("/api/v1/scans/99999/export", headers=auth_headers)
    assert response.status_code == 404
