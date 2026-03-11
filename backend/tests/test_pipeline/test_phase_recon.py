"""Tests for Phase 1: Reconnaissance functions."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ToolExecutionError
from app.models.base import ScanStatus, TargetType
from app.models.scan import Scan
from app.models.target import Target
from app.models.user import User
from app.pipeline.engine import EventEmitter
from app.pipeline.parsers import AmassResult, HarvesterResult
from app.pipeline.phase_recon import run_amass, run_dnsx, run_phase_recon, run_theharvester


@pytest_asyncio.fixture
async def scan_user(db_session: AsyncSession) -> User:
    from app.core.security import hash_password

    user = User(
        username="recon_test_user",
        email="recon@example.com",
        hashed_password=hash_password("test"),
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_scan(db_session: AsyncSession, scan_user: User) -> Scan:
    scan = Scan(
        scan_uid="recon-test-001",
        target_domain="example.com",
        status=ScanStatus.RUNNING,
        current_phase=1,
        config={"target_domain": "example.com"},
        results_dir="/results/recon-test-001",
        created_by=scan_user.id,
    )
    db_session.add(scan)
    await db_session.commit()
    await db_session.refresh(scan)
    return scan


class TestRunTheHarvester:
    """Tests for the theHarvester tool runner."""

    @pytest.mark.asyncio
    async def test_successful_run(self):
        """Successful theHarvester run should parse and return results."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(return_value=(0, "completed"))
        docker.read_file_from_container = AsyncMock(
            return_value=json.dumps({
                "hosts": ["sub1.example.com", "sub2.example.com"],
                "ips": ["1.2.3.4"],
                "emails": ["user@example.com"],
            })
        )
        emitter = AsyncMock(spec=EventEmitter)
        emitter.emit = AsyncMock()

        config = {"target_domain": "example.com", "harvester_sources": "bing,crtsh"}
        result = await run_theharvester(docker, config, "/results/test", emitter)

        assert isinstance(result, HarvesterResult)
        assert len(result.subdomains) == 2
        assert len(result.ips) == 1
        assert len(result.emails) == 1

        # Verify events
        event_names = [call[0][0] for call in emitter.emit.call_args_list]
        assert "tool_started" in event_names
        assert "tool_completed" in event_names
        assert "tool_result" in event_names

    @pytest.mark.asyncio
    async def test_tool_failure_raises(self):
        """Non-zero exit code should raise ToolExecutionError."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(side_effect=[
            (0, "mkdir ok"),  # mkdir
            (1, "theHarvester error"),  # tool run
        ])
        emitter = AsyncMock(spec=EventEmitter)
        emitter.emit = AsyncMock()

        config = {"target_domain": "example.com"}
        with pytest.raises(ToolExecutionError):
            await run_theharvester(docker, config, "/results/test", emitter)


class TestRunAmass:
    """Tests for the Amass tool runner."""

    @pytest.mark.asyncio
    async def test_successful_run(self):
        """Successful Amass run should parse v4 graph-format and return results."""
        amass_output = "\n".join([
            "sub1.example.com (FQDN) --> a_record --> 1.2.3.4 (IPAddress)",
            "sub2.example.com (FQDN) --> a_record --> 5.6.7.8 (IPAddress)",
        ])
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(return_value=(0, "completed"))
        docker.read_file_from_container = AsyncMock(return_value=amass_output)
        emitter = AsyncMock(spec=EventEmitter)
        emitter.emit = AsyncMock()

        config = {"target_domain": "example.com", "amass_timeout": 5}
        result = await run_amass(docker, config, "/results/test", emitter)

        assert isinstance(result, AmassResult)
        assert len(result.subdomains) == 2
        assert len(result.ips) == 2


class TestRunDnsx:
    """Tests for the dnsx DNS resolution runner."""

    @pytest.mark.asyncio
    async def test_successful_resolution(self):
        """dnsx should return subdomain-to-IP mapping."""
        dnsx_output = "\n".join([
            json.dumps({"host": "sub1.example.com", "a": ["1.2.3.4"]}),
            json.dumps({"host": "sub2.example.com", "a": ["5.6.7.8"]}),
        ])
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(return_value=(0, "ok"))
        docker.read_file_from_container = AsyncMock(return_value=dnsx_output)
        emitter = AsyncMock(spec=EventEmitter)
        emitter.emit = AsyncMock()

        result = await run_dnsx(docker, ["sub1.example.com", "sub2.example.com"], "/results/test", emitter)

        assert "sub1.example.com" in result
        assert result["sub1.example.com"] == ["1.2.3.4"]

    @pytest.mark.asyncio
    async def test_empty_subdomains_returns_empty(self):
        """No subdomains should return empty dict without calling dnsx."""
        docker = AsyncMock()
        emitter = AsyncMock(spec=EventEmitter)
        emitter.emit = AsyncMock()

        result = await run_dnsx(docker, [], "/results/test", emitter)
        assert result == {}
        docker.exec_in_container.assert_not_called()


class TestRunPhaseRecon:
    """Tests for the Phase 1 orchestrator."""

    @pytest.mark.asyncio
    async def test_phase_saves_targets_to_db(self, test_scan, db_session):
        """run_phase_recon should save discovered targets to the database."""
        from tests.conftest import test_session_factory

        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(return_value=(0, "ok"))

        # Mock file reads for parsers
        harvester_json = json.dumps({
            "hosts": ["sub1.example.com"],
            "ips": ["1.2.3.4"],
            "emails": ["user@example.com"],
        })
        amass_output = "sub2.example.com (FQDN) --> a_record --> 5.6.7.8 (IPAddress)"
        dnsx_output = json.dumps({"host": "sub1.example.com", "a": ["1.2.3.4"]})

        # Set up sequential return values for read_file_from_container
        docker.read_file_from_container = AsyncMock(
            side_effect=[
                harvester_json,  # theHarvester output
                amass_output,  # Amass output (v4 graph format)
                dnsx_output,  # dnsx output
            ]
        )

        emitter = AsyncMock(spec=EventEmitter)
        emitter.emit = AsyncMock()

        await run_phase_recon(
            docker=docker,
            config=test_scan.config,
            results_dir=test_scan.results_dir,
            emitter=emitter,
            db_session_factory=test_session_factory,
            scan_id=test_scan.id,
        )

        # Check targets were saved
        result = await db_session.execute(
            select(Target).where(Target.scan_id == test_scan.id)
        )
        targets = list(result.scalars())
        assert len(targets) > 0

        # Should have subdomains, IPs, and emails
        types = {t.target_type for t in targets}
        assert TargetType.SUBDOMAIN in types
        assert TargetType.IP in types
        assert TargetType.EMAIL in types

    @pytest.mark.asyncio
    async def test_phase_continues_when_one_tool_fails(self, test_scan, db_session):
        """If theHarvester fails but Amass succeeds, phase should still save results."""
        from tests.conftest import test_session_factory

        docker = AsyncMock()

        # theHarvester fails (mkdir succeeds, tool fails)
        call_count = 0

        async def mock_exec(container, command, **kwargs):
            nonlocal call_count
            call_count += 1
            if container == "theharvester" and "theHarvester" in command:
                return (1, "tool error")
            return (0, "ok")

        docker.exec_in_container = AsyncMock(side_effect=mock_exec)

        # Amass succeeds (v4 graph format)
        amass_output = "sub1.example.com (FQDN) --> a_record --> 1.2.3.4 (IPAddress)"
        docker.read_file_from_container = AsyncMock(
            side_effect=[
                amass_output,  # Amass output (v4 graph format)
                "",  # dnsx (empty)
            ]
        )

        emitter = AsyncMock(spec=EventEmitter)
        emitter.emit = AsyncMock()

        # Should not raise even though theHarvester failed
        await run_phase_recon(
            docker=docker,
            config=test_scan.config,
            results_dir=test_scan.results_dir,
            emitter=emitter,
            db_session_factory=test_session_factory,
            scan_id=test_scan.id,
        )

        # Should still have targets from Amass
        result = await db_session.execute(
            select(Target).where(Target.scan_id == test_scan.id)
        )
        targets = list(result.scalars())
        assert len(targets) > 0
