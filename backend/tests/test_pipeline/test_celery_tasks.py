"""Tests for Celery task definitions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ToolExecutionError
from app.tasks.celery_app import celery_app


class TestCeleryApp:
    """Tests for the Celery app configuration."""

    def test_celery_app_exists(self):
        """Celery app should be properly configured."""
        assert celery_app.main == "cybersec_pipeline"

    def test_task_serializer_is_json(self):
        """Tasks should serialize as JSON."""
        assert celery_app.conf.task_serializer == "json"

    def test_task_acks_late_enabled(self):
        """Global task_acks_late should be True for reliability."""
        assert celery_app.conf.task_acks_late is True

    def test_worker_prefetch_multiplier_is_one(self):
        """Worker should only prefetch 1 task at a time."""
        assert celery_app.conf.worker_prefetch_multiplier == 1

    def test_includes_task_modules(self):
        """Celery should include scan_tasks and maintenance modules."""
        includes = celery_app.conf.include
        assert "app.tasks.scan_tasks" in includes
        assert "app.tasks.maintenance" in includes


class TestScanTask:
    """Tests for the run_scan_task Celery task."""

    def test_task_is_registered(self):
        """run_scan_task should be discoverable as a Celery task."""
        from app.tasks.scan_tasks import run_scan_task
        assert run_scan_task.name is not None

    def test_task_has_acks_late(self):
        """run_scan_task should have acks_late=True."""
        from app.tasks.scan_tasks import run_scan_task
        assert run_scan_task.acks_late is True

    def test_task_has_reject_on_worker_lost(self):
        """run_scan_task should have reject_on_worker_lost=True."""
        from app.tasks.scan_tasks import run_scan_task
        assert run_scan_task.reject_on_worker_lost is True

    @patch("app.tasks.scan_tasks._run_pipeline", new_callable=AsyncMock)
    def test_task_calls_pipeline(self, mock_pipeline):
        """run_scan_task should invoke the pipeline engine."""
        from app.tasks.scan_tasks import run_scan_task

        # Run the task synchronously (Celery's .apply method)
        with patch("app.tasks.scan_tasks.asyncio") as mock_asyncio:
            mock_asyncio.run = MagicMock()
            result = run_scan_task.apply(args=[42])

            # asyncio.run should have been called
            mock_asyncio.run.assert_called()

    @patch("app.tasks.scan_tasks._run_pipeline", new_callable=AsyncMock)
    def test_task_returns_completed_on_success(self, mock_pipeline):
        """Successful task should return status=completed."""
        from app.tasks.scan_tasks import run_scan_task

        with patch("app.tasks.scan_tasks.asyncio") as mock_asyncio:
            mock_asyncio.run = MagicMock(return_value=None)
            result = run_scan_task.apply(args=[42])

            assert result.result["status"] == "completed"
            assert result.result["scan_id"] == 42

    @patch("app.tasks.scan_tasks._run_pipeline", new_callable=AsyncMock)
    @patch("app.tasks.scan_tasks._mark_scan_failed", new_callable=AsyncMock)
    def test_task_returns_failed_on_unrecoverable_error(self, mock_mark_failed, mock_pipeline):
        """Unrecoverable errors should mark scan as failed."""
        from app.tasks.scan_tasks import run_scan_task

        with patch("app.tasks.scan_tasks.asyncio") as mock_asyncio:
            mock_asyncio.run = MagicMock(side_effect=[RuntimeError("kaboom"), None])
            result = run_scan_task.apply(args=[42])

            assert result.result["status"] == "failed"
            assert "kaboom" in result.result["error"]
            assert result.result["exception_type"] == "RuntimeError"

    @patch("app.tasks.scan_tasks._run_pipeline", new_callable=AsyncMock)
    @patch("app.tasks.scan_tasks._mark_scan_failed", new_callable=AsyncMock)
    def test_task_marks_failed_even_when_mark_fails(self, mock_mark_failed, mock_pipeline):
        """Task should handle failure in _mark_scan_failed gracefully."""
        from app.tasks.scan_tasks import run_scan_task

        with patch("app.tasks.scan_tasks.asyncio") as mock_asyncio:
            # Pipeline fails, then mark_scan_failed also fails
            mock_asyncio.run = MagicMock(
                side_effect=[RuntimeError("pipeline boom"), Exception("DB unreachable")]
            )
            result = run_scan_task.apply(args=[42])

            # Task should still return a result (not crash)
            assert result.result["status"] == "failed"


class TestMarkScanFailed:
    """Tests for the _mark_scan_failed last-resort handler."""

    @pytest.mark.asyncio
    async def test_marks_pending_scan_as_failed(self, db_session):
        """Should mark a PENDING/RUNNING scan as FAILED."""
        from app.models.base import ScanStatus
        from app.models.scan import Scan
        from app.models.user import User
        from app.core.security import hash_password
        from app.tasks.scan_tasks import _mark_scan_failed
        from sqlalchemy import select
        from tests.conftest import test_session_factory

        user = User(
            username="task_test_user",
            email="task@example.com",
            hashed_password=hash_password("test"),
            is_active=True,
            is_admin=False,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        scan = Scan(
            scan_uid="task-fail-001",
            target_domain="example.com",
            status=ScanStatus.RUNNING,
            current_phase=1,
            config={},
            results_dir="/results/task-fail-001",
            created_by=user.id,
        )
        db_session.add(scan)
        await db_session.commit()
        await db_session.refresh(scan)

        # Patch the session factory used inside _mark_scan_failed
        with patch("app.tasks.scan_tasks.async_session_factory", test_session_factory):
            await _mark_scan_failed(scan.id, "Something went wrong")

        # Verify scan was marked as failed
        result = await db_session.execute(select(Scan).where(Scan.id == scan.id))
        updated_scan = result.scalar_one()
        assert updated_scan.status == ScanStatus.FAILED
        assert "Something went wrong" in updated_scan.error_message
        assert updated_scan.completed_at is not None

    @pytest.mark.asyncio
    async def test_does_not_overwrite_terminal_state(self, db_session):
        """Should not overwrite COMPLETED/FAILED/CANCELLED state."""
        from app.models.base import ScanStatus
        from app.models.scan import Scan
        from app.models.user import User
        from app.core.security import hash_password
        from app.tasks.scan_tasks import _mark_scan_failed
        from sqlalchemy import select
        from tests.conftest import test_session_factory

        user = User(
            username="task_test_user2",
            email="task2@example.com",
            hashed_password=hash_password("test"),
            is_active=True,
            is_admin=False,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        scan = Scan(
            scan_uid="task-completed-001",
            target_domain="example.com",
            status=ScanStatus.COMPLETED,
            current_phase=4,
            config={},
            results_dir="/results/task-completed-001",
            created_by=user.id,
        )
        db_session.add(scan)
        await db_session.commit()
        await db_session.refresh(scan)

        with patch("app.tasks.scan_tasks.async_session_factory", test_session_factory):
            await _mark_scan_failed(scan.id, "Late error after completion")

        # Should still be COMPLETED
        result = await db_session.execute(select(Scan).where(Scan.id == scan.id))
        updated_scan = result.scalar_one()
        assert updated_scan.status == ScanStatus.COMPLETED


class TestMaintenanceTask:
    """Tests for maintenance tasks."""

    def test_nuclei_update_task_exists(self):
        """update_nuclei_templates should be a registered task."""
        from app.tasks.maintenance import update_nuclei_templates
        assert update_nuclei_templates.name is not None
