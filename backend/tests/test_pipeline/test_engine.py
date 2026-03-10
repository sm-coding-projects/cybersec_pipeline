"""Tests for the PipelineEngine state machine."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ToolExecutionError
from app.models.base import PhaseStatus, ScanStatus
from app.models.scan import Scan, ScanPhase
from app.models.user import User
from app.pipeline.engine import EventEmitter, PipelineEngine
from app.pipeline.utils import ToolTimeout


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def scan_user(db_session: AsyncSession) -> User:
    """Create a user for scan ownership."""
    from app.core.security import hash_password

    user = User(
        username="pipeline_test_user",
        email="pipeline@example.com",
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
    """Create a test scan in PENDING state."""
    scan = Scan(
        scan_uid="test-scan-001",
        target_domain="example.com",
        status=ScanStatus.PENDING,
        current_phase=0,
        config={"target_domain": "example.com"},
        results_dir="/results/test-scan-001",
        created_by=scan_user.id,
    )
    db_session.add(scan)
    await db_session.commit()
    await db_session.refresh(scan)
    return scan


def _make_engine(scan_id: int) -> PipelineEngine:
    """Create a PipelineEngine with mocked Docker and Redis dependencies."""
    from tests.conftest import test_session_factory

    engine = PipelineEngine(
        scan_id=scan_id,
        db_session_factory=test_session_factory,
    )
    engine.docker = MagicMock()
    engine.docker.close = MagicMock()
    engine.emitter = AsyncMock(spec=EventEmitter)
    engine.emitter.emit = AsyncMock()
    engine.emitter.close = AsyncMock()
    return engine


# ── EventEmitter tests ───────────────────────────────────────────────


class TestEventEmitter:
    """Tests for the EventEmitter Redis pub/sub wrapper."""

    @pytest.mark.asyncio
    async def test_emit_publishes_to_correct_channel(self):
        """Emit should publish JSON to scan_events:{scan_id}."""
        emitter = EventEmitter(scan_id=42)
        mock_redis = AsyncMock()
        emitter._redis = mock_redis

        await emitter.emit("tool_started", {"tool": "nmap"})

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "scan_events:42"
        payload = json.loads(call_args[0][1])
        assert payload["event"] == "tool_started"
        assert payload["data"]["tool"] == "nmap"

    @pytest.mark.asyncio
    async def test_emit_handles_redis_failure_gracefully(self):
        """Emit should not raise if Redis is unavailable."""
        emitter = EventEmitter(scan_id=99)
        mock_redis = AsyncMock()
        mock_redis.publish.side_effect = ConnectionError("Redis down")
        emitter._redis = mock_redis

        # Should not raise
        await emitter.emit("test_event", {"key": "value"})

    @pytest.mark.asyncio
    async def test_emit_with_no_data(self):
        """Emit with None data should send empty dict."""
        emitter = EventEmitter(scan_id=1)
        mock_redis = AsyncMock()
        emitter._redis = mock_redis

        await emitter.emit("scan_started")

        payload = json.loads(mock_redis.publish.call_args[0][1])
        assert payload["data"] == {}


# ── PipelineEngine tests ─────────────────────────────────────────────


class TestPipelineEngine:
    """Tests for the PipelineEngine state machine."""

    @pytest.mark.asyncio
    async def test_engine_runs_all_phases_successfully(self, test_scan, db_session):
        """Engine should run all 4 phases and mark scan as COMPLETED."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None  # Not cancelled
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock) as mock_recon, \
                 patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock) as mock_network, \
                 patch("app.pipeline.phase_vulnscan.run_phase_vulnscan", new_callable=AsyncMock) as mock_vulnscan, \
                 patch("app.pipeline.phase_report.run_phase_report", new_callable=AsyncMock) as mock_report:

                await engine.run()

                # Verify all phases were called
                mock_recon.assert_called_once()
                mock_network.assert_called_once()
                mock_vulnscan.assert_called_once()
                mock_report.assert_called_once()

        # Verify scan status was updated to COMPLETED
        result = await db_session.execute(select(Scan).where(Scan.id == test_scan.id))
        scan = result.scalar_one()
        assert scan.status == ScanStatus.COMPLETED

        # Verify events were emitted
        event_calls = [call[0][0] for call in engine.emitter.emit.call_args_list]
        assert "scan_started" in event_calls
        assert "pipeline_complete" in event_calls

    @pytest.mark.asyncio
    async def test_engine_handles_phase_failure(self, test_scan, db_session):
        """When a phase fails, engine should mark scan as FAILED and stop."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock) as mock_recon:
                mock_recon.side_effect = Exception("Recon exploded")

                with patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock) as mock_network:
                    await engine.run()

                    # Network phase should NOT have been called
                    mock_network.assert_not_called()

        # Scan should be FAILED
        result = await db_session.execute(select(Scan).where(Scan.id == test_scan.id))
        scan = result.scalar_one()
        assert scan.status == ScanStatus.FAILED
        assert "Recon exploded" in scan.error_message

    @pytest.mark.asyncio
    async def test_engine_handles_tool_execution_error(self, test_scan, db_session):
        """ToolExecutionError should be handled with tool-specific details."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock) as mock_recon:
                mock_recon.side_effect = ToolExecutionError(
                    tool="theharvester",
                    message="Process killed",
                    exit_code=137,
                )

                with patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock) as mock_network:
                    await engine.run()
                    mock_network.assert_not_called()

        # Scan should be FAILED
        result = await db_session.execute(select(Scan).where(Scan.id == test_scan.id))
        scan = result.scalar_one()
        assert scan.status == ScanStatus.FAILED

        # scan_failed event should include tool context
        scan_failed_calls = [
            call for call in engine.emitter.emit.call_args_list
            if call[0][0] == "scan_failed"
        ]
        assert len(scan_failed_calls) == 1
        event_data = scan_failed_calls[0][0][1]
        assert event_data["tool"] == "theharvester"
        assert event_data["phase"] == "recon"
        assert event_data["exception_type"] == "ToolExecutionError"

    @pytest.mark.asyncio
    async def test_engine_handles_tool_timeout(self, test_scan, db_session):
        """ToolTimeout should be handled with timeout-specific details."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock) as mock_network:
                mock_network.side_effect = ToolTimeout(tool="nmap", timeout_seconds=600)

                with patch("app.pipeline.phase_vulnscan.run_phase_vulnscan", new_callable=AsyncMock) as mock_vulnscan:
                    await engine.run()
                    mock_vulnscan.assert_not_called()

        # Scan should be FAILED
        result = await db_session.execute(select(Scan).where(Scan.id == test_scan.id))
        scan = result.scalar_one()
        assert scan.status == ScanStatus.FAILED

        # scan_failed event should have timeout info
        scan_failed_calls = [
            call for call in engine.emitter.emit.call_args_list
            if call[0][0] == "scan_failed"
        ]
        assert len(scan_failed_calls) == 1
        event_data = scan_failed_calls[0][0][1]
        assert event_data["exception_type"] == "ToolTimeout"

    @pytest.mark.asyncio
    async def test_engine_cancellation_before_first_phase(self, test_scan, db_session):
        """Engine should stop if cancellation flag is set in Redis before any phase."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            # Return a value to indicate cancellation
            mock_redis_instance.get.return_value = "1"
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock) as mock_recon:
                await engine.run()

                # Recon should NOT have been called because cancellation is checked first
                mock_recon.assert_not_called()

        # Scan should be CANCELLED
        result = await db_session.execute(select(Scan).where(Scan.id == test_scan.id))
        scan = result.scalar_one()
        assert scan.status == ScanStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_engine_cancellation_between_phases(self, test_scan, db_session):
        """Engine should stop between phases when cancellation flag is set."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            # Not cancelled before recon, cancelled before network
            mock_redis_instance.get.side_effect = [None, "1"]
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock) as mock_recon, \
                 patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock) as mock_network:
                await engine.run()

                mock_recon.assert_called_once()
                mock_network.assert_not_called()

        # Scan should be CANCELLED
        result = await db_session.execute(select(Scan).where(Scan.id == test_scan.id))
        scan = result.scalar_one()
        assert scan.status == ScanStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_engine_cancellation_during_phase_via_asyncio(self, test_scan, db_session):
        """Engine should handle asyncio.CancelledError during a phase."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock) as mock_recon:
                mock_recon.side_effect = asyncio.CancelledError()

                with patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock) as mock_network:
                    await engine.run()
                    mock_network.assert_not_called()

        result = await db_session.execute(select(Scan).where(Scan.id == test_scan.id))
        scan = result.scalar_one()
        assert scan.status == ScanStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_engine_report_failure_is_nonfatal(self, test_scan, db_session):
        """Report phase failure should not fail the entire scan."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_vulnscan.run_phase_vulnscan", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_report.run_phase_report", new_callable=AsyncMock) as mock_report:

                mock_report.side_effect = Exception("DefectDojo unreachable")
                await engine.run()

        # Scan should still be COMPLETED because report is non-fatal
        result = await db_session.execute(select(Scan).where(Scan.id == test_scan.id))
        scan = result.scalar_one()
        assert scan.status == ScanStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_engine_report_tool_timeout_is_nonfatal(self, test_scan, db_session):
        """Report phase ToolTimeout should not fail the entire scan."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_vulnscan.run_phase_vulnscan", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_report.run_phase_report", new_callable=AsyncMock) as mock_report:

                mock_report.side_effect = ToolTimeout(tool="defectdojo", timeout_seconds=300)
                await engine.run()

        result = await db_session.execute(select(Scan).where(Scan.id == test_scan.id))
        scan = result.scalar_one()
        assert scan.status == ScanStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_engine_report_tool_execution_error_is_nonfatal(self, test_scan, db_session):
        """Report phase ToolExecutionError should not fail the entire scan."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_vulnscan.run_phase_vulnscan", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_report.run_phase_report", new_callable=AsyncMock) as mock_report:

                mock_report.side_effect = ToolExecutionError(tool="defectdojo", message="API error", exit_code=500)
                await engine.run()

        result = await db_session.execute(select(Scan).where(Scan.id == test_scan.id))
        scan = result.scalar_one()
        assert scan.status == ScanStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_engine_creates_phase_records(self, test_scan, db_session):
        """Engine should create ScanPhase records for each phase."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_vulnscan.run_phase_vulnscan", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_report.run_phase_report", new_callable=AsyncMock):
                await engine.run()

        # Check that 4 phase records were created
        result = await db_session.execute(
            select(ScanPhase).where(ScanPhase.scan_id == test_scan.id).order_by(ScanPhase.phase_number)
        )
        phases = list(result.scalars())
        assert len(phases) == 4
        assert phases[0].phase_name == "recon"
        assert phases[1].phase_name == "network"
        assert phases[2].phase_name == "vulnscan"
        assert phases[3].phase_name == "report"

        # All should be completed
        for phase in phases:
            assert phase.status == PhaseStatus.COMPLETED
            assert phase.started_at is not None
            assert phase.completed_at is not None

    @pytest.mark.asyncio
    async def test_engine_nonexistent_scan(self, db_session):
        """Engine should handle gracefully when scan doesn't exist."""
        engine = _make_engine(99999)

        # Should not raise
        await engine.run()

        # No events should be emitted (engine returns early)
        engine.emitter.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_engine_failed_phase_record_has_error_message(self, test_scan, db_session):
        """When a phase fails, its ScanPhase record should contain the error."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock) as mock_recon, \
                 patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock):
                mock_recon.side_effect = ToolExecutionError(
                    tool="amass", message="DNS resolution failed", exit_code=1
                )
                await engine.run()

        result = await db_session.execute(
            select(ScanPhase).where(
                ScanPhase.scan_id == test_scan.id,
                ScanPhase.phase_number == 1,
            )
        )
        phase = result.scalar_one()
        assert phase.status == PhaseStatus.FAILED
        assert phase.error_message is not None
        assert "DNS resolution failed" in phase.error_message

    @pytest.mark.asyncio
    async def test_engine_cleanup_called_on_success(self, test_scan, db_session):
        """The _cleanup method should be called even on success."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_vulnscan.run_phase_vulnscan", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_report.run_phase_report", new_callable=AsyncMock):
                await engine.run()

        # Emitter close should have been called (by _cleanup)
        engine.emitter.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_engine_cleanup_called_on_failure(self, test_scan, db_session):
        """The _cleanup method should be called even when the pipeline fails."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock) as mock_recon:
                mock_recon.side_effect = Exception("Boom!")
                with patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock):
                    await engine.run()

        # Emitter close should still have been called
        engine.emitter.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_engine_scan_failed_event_includes_traceback(self, test_scan, db_session):
        """The scan_failed event should include exception type and traceback."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock) as mock_recon, \
                 patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock):
                mock_recon.side_effect = ValueError("bad config value")
                await engine.run()

        scan_failed_calls = [
            call for call in engine.emitter.emit.call_args_list
            if call[0][0] == "scan_failed"
        ]
        assert len(scan_failed_calls) == 1
        event_data = scan_failed_calls[0][0][1]
        assert event_data["exception_type"] == "ValueError"
        assert "traceback" in event_data
        assert "bad config value" in event_data["error"]


# ── Full pipeline integration test (mocked) ─────────────────────────


class TestPipelineIntegration:
    """Integration-style tests with all phases mocked at the tool level."""

    @pytest.mark.asyncio
    async def test_full_pipeline_success_flow(self, test_scan, db_session):
        """Simulate a complete successful pipeline run with all events."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_vulnscan.run_phase_vulnscan", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_report.run_phase_report", new_callable=AsyncMock):
                await engine.run()

        # Verify the full lifecycle of events
        event_names = [call[0][0] for call in engine.emitter.emit.call_args_list]

        # Scan lifecycle
        assert event_names[0] == "scan_started"
        assert event_names[-1] == "pipeline_complete"

        # Each phase should have started and completed
        assert event_names.count("phase_started") == 4
        assert event_names.count("phase_completed") == 4

        # Verify scan state
        result = await db_session.execute(select(Scan).where(Scan.id == test_scan.id))
        scan = result.scalar_one()
        assert scan.status == ScanStatus.COMPLETED
        assert scan.started_at is not None
        assert scan.completed_at is not None

        # Verify all phase records
        phase_result = await db_session.execute(
            select(ScanPhase).where(ScanPhase.scan_id == test_scan.id).order_by(ScanPhase.phase_number)
        )
        phases = list(phase_result.scalars())
        assert len(phases) == 4
        for phase in phases:
            assert phase.status == PhaseStatus.COMPLETED
            assert phase.duration_seconds is not None
            assert phase.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_pipeline_partial_failure_continues_to_report(self, test_scan, db_session):
        """When vulnscan fails, pipeline should fail before report."""
        engine = _make_engine(test_scan.id)

        with patch("app.pipeline.engine.aioredis") as mock_aioredis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.get.return_value = None
            mock_aioredis.from_url.return_value = mock_redis_instance

            with patch("app.pipeline.phase_recon.run_phase_recon", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_network.run_phase_network", new_callable=AsyncMock), \
                 patch("app.pipeline.phase_vulnscan.run_phase_vulnscan", new_callable=AsyncMock) as mock_vulnscan, \
                 patch("app.pipeline.phase_report.run_phase_report", new_callable=AsyncMock) as mock_report:
                mock_vulnscan.side_effect = ToolExecutionError(
                    tool="nuclei", message="Template loading error", exit_code=1
                )
                await engine.run()

                mock_report.assert_not_called()

        result = await db_session.execute(select(Scan).where(Scan.id == test_scan.id))
        scan = result.scalar_one()
        assert scan.status == ScanStatus.FAILED

        # First two phases should be completed, vulnscan should be failed
        phase_result = await db_session.execute(
            select(ScanPhase).where(ScanPhase.scan_id == test_scan.id).order_by(ScanPhase.phase_number)
        )
        phases = list(phase_result.scalars())
        assert len(phases) == 3  # Report phase never started
        assert phases[0].status == PhaseStatus.COMPLETED  # recon
        assert phases[1].status == PhaseStatus.COMPLETED  # network
        assert phases[2].status == PhaseStatus.FAILED  # vulnscan
