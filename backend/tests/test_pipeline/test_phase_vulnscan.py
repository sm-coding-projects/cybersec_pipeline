"""Tests for Phase 3: Vulnerability Scanning functions."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ToolExecutionError
from app.models.base import ScanStatus, Severity, TargetType
from app.models.finding import Finding
from app.models.scan import Scan
from app.models.target import Target
from app.models.user import User
from app.pipeline.engine import EventEmitter
from app.pipeline.parsers import NucleiFinding
from app.pipeline.phase_vulnscan import run_nuclei, run_phase_vulnscan


@pytest_asyncio.fixture
async def scan_user(db_session: AsyncSession) -> User:
    from app.core.security import hash_password

    user = User(
        username="vulnscan_test_user",
        email="vulnscan@example.com",
        hashed_password=hash_password("test"),
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_scan_with_urls(db_session: AsyncSession, scan_user: User) -> Scan:
    """Create a scan with URL targets for vulnerability scanning."""
    scan = Scan(
        scan_uid="vulnscan-test-001",
        target_domain="example.com",
        status=ScanStatus.RUNNING,
        current_phase=3,
        config={"target_domain": "example.com", "enable_zap": False},
        results_dir="/results/vulnscan-test-001",
        created_by=scan_user.id,
    )
    db_session.add(scan)
    await db_session.commit()
    await db_session.refresh(scan)

    # Add URL targets
    for url in ["https://example.com", "https://sub.example.com"]:
        target = Target(
            scan_id=scan.id,
            target_type=TargetType.URL,
            value=url,
            source_tool="httpx",
            is_live=True,
        )
        db_session.add(target)
    await db_session.commit()

    return scan


class TestRunNuclei:
    """Tests for the Nuclei tool runner."""

    @pytest.mark.asyncio
    async def test_successful_run(self):
        """Successful Nuclei run should parse JSONL and return findings."""
        nuclei_jsonl = "\n".join([
            json.dumps({
                "template-id": "cve-2024-1234",
                "info": {"name": "Test CVE", "severity": "high", "description": "A test CVE", "reference": ["https://ref.com"]},
                "host": "example.com",
                "matched-at": "https://example.com/vuln",
            }),
            json.dumps({
                "template-id": "tech-detect",
                "info": {"name": "Tech Detect", "severity": "info", "description": "Tech found"},
                "host": "example.com",
                "matched-at": "https://example.com",
            }),
        ])
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(return_value=(0, "completed"))
        docker.read_file_from_container = AsyncMock(return_value=nuclei_jsonl)
        emitter = AsyncMock(spec=EventEmitter)
        emitter.emit = AsyncMock()

        config = {"nuclei_rate_limit": 100, "nuclei_severities": "critical,high,medium"}
        urls = ["https://example.com"]
        findings = await run_nuclei(docker, urls, config, "/results/test", emitter)

        assert len(findings) == 2
        assert findings[0].severity == Severity.HIGH
        assert findings[0].template_id == "cve-2024-1234"
        assert findings[1].severity == Severity.INFO

        # High severity should trigger finding_discovered event
        event_calls = [call[0] for call in emitter.emit.call_args_list]
        event_names = [c[0] for c in event_calls]
        assert "finding_discovered" in event_names

    @pytest.mark.asyncio
    async def test_empty_urls_returns_empty(self):
        """No URLs should return empty list without calling Nuclei."""
        docker = AsyncMock()
        emitter = AsyncMock(spec=EventEmitter)
        emitter.emit = AsyncMock()

        result = await run_nuclei(docker, [], {}, "/results/test", emitter)
        assert result == []
        docker.exec_in_container.assert_not_called()


class TestRunPhaseVulnscan:
    """Tests for the Phase 3 orchestrator."""

    @pytest.mark.asyncio
    async def test_phase_saves_findings_to_db(self, test_scan_with_urls, db_session):
        """run_phase_vulnscan should save nuclei findings to the database."""
        from tests.conftest import test_session_factory

        nuclei_jsonl = json.dumps({
            "template-id": "cve-2024-5678",
            "info": {"name": "Critical CVE", "severity": "critical", "description": "Very bad"},
            "host": "example.com",
            "matched-at": "https://example.com",
        })

        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(return_value=(0, "ok"))
        docker.read_file_from_container = AsyncMock(return_value=nuclei_jsonl)
        emitter = AsyncMock(spec=EventEmitter)
        emitter.emit = AsyncMock()

        await run_phase_vulnscan(
            docker=docker,
            config=test_scan_with_urls.config,
            results_dir=test_scan_with_urls.results_dir,
            emitter=emitter,
            db_session_factory=test_session_factory,
            scan_id=test_scan_with_urls.id,
        )

        # Check findings were saved
        result = await db_session.execute(
            select(Finding).where(Finding.scan_id == test_scan_with_urls.id)
        )
        findings = list(result.scalars())
        assert len(findings) == 1
        assert findings[0].severity == Severity.CRITICAL
        assert findings[0].source_tool == "nuclei"
        assert findings[0].template_id == "cve-2024-5678"

    @pytest.mark.asyncio
    async def test_phase_handles_no_urls_gracefully(self, db_session):
        """Phase should handle scan with no URL targets gracefully."""
        from app.core.security import hash_password
        from tests.conftest import test_session_factory

        user = User(
            username="nourl_user",
            email="nourl@example.com",
            hashed_password=hash_password("test"),
            is_active=True,
            is_admin=False,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        scan = Scan(
            scan_uid="no-urls-001",
            target_domain="empty.com",
            status=ScanStatus.RUNNING,
            current_phase=3,
            config={"target_domain": "empty.com", "enable_zap": False},
            results_dir="/results/no-urls-001",
            created_by=user.id,
        )
        db_session.add(scan)
        await db_session.commit()
        await db_session.refresh(scan)

        docker = AsyncMock()
        emitter = AsyncMock(spec=EventEmitter)
        emitter.emit = AsyncMock()

        # Should not raise
        await run_phase_vulnscan(
            docker=docker,
            config=scan.config,
            results_dir=scan.results_dir,
            emitter=emitter,
            db_session_factory=test_session_factory,
            scan_id=scan.id,
        )

        # No findings saved
        result = await db_session.execute(
            select(Finding).where(Finding.scan_id == scan.id)
        )
        assert len(list(result.scalars())) == 0
