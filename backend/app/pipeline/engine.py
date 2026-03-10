"""Pipeline engine — the state machine that orchestrates 4-phase scans.

Called by the Celery task ``run_scan_task``, NOT directly by API handlers.
The engine runs phases sequentially, emits real-time events via Redis
pub/sub, and persists status to PostgreSQL.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.base import PhaseStatus, ScanStatus
from app.models.scan import Scan, ScanPhase
from app.services.docker_manager import DockerManager

logger = logging.getLogger(__name__)

# Phase definitions: (phase_number, phase_name)
PHASES: list[tuple[int, str]] = [
    (1, "recon"),
    (2, "network"),
    (3, "vulnscan"),
    (4, "report"),
]


class EventEmitter:
    """Publishes scan events to Redis pub/sub.

    Channel: ``scan_events:{scan_id}``
    Message format: ``{"event": "<event_name>", "data": {...}}``

    The FastAPI WebSocket endpoint subscribes to this channel and
    forwards events to connected browsers.
    """

    # Events that represent a tool status transition
    _TOOL_STATUS_EVENTS: dict[str, str] = {
        "tool_started": "running",
        "tool_completed": "completed",
        "tool_error": "error",
        "tool_skipped": "skipped",
    }

    def __init__(
        self,
        scan_id: int,
        db_session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.scan_id = scan_id
        self.channel = f"scan_events:{scan_id}"
        self._redis: aioredis.Redis | None = None
        # In-memory tracking of tool statuses for the current phase
        self.tool_statuses: dict[str, str] = {}
        # DB session factory for persisting tool statuses mid-phase so that
        # the REST API always reflects live state (not just on phase completion)
        self._db_session_factory = db_session_factory
        # Live state snapshot persisted to Redis so late-joining WS clients
        # can receive a full picture of what has happened so far.
        # Includes rolling log buffer so logs survive navigation.
        self._live_state: dict[str, Any] = {
            "current_phase": 0,
            "phase_statuses": {},
            "tool_statuses": {},
            "logs": [],
        }

    def reset_tool_statuses(self) -> None:
        """Reset tool status tracking between phases."""
        self.tool_statuses = {}

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        """Publish an event to the scan's Redis pub/sub channel."""
        data = data or {}
        is_tool_status_event = event in self._TOOL_STATUS_EVENTS and "tool" in data

        # Track tool status transitions in memory so engine can persist them
        if is_tool_status_event:
            self.tool_statuses[data["tool"]] = self._TOOL_STATUS_EVENTS[event]

        # Update live state snapshot so late-joining WS clients get current state
        self._update_live_state(event, data)

        message = json.dumps({"event": event, "data": data})
        try:
            r = await self._get_redis()
            await r.publish(self.channel, message)
            # Persist live snapshot; 24h TTL covers any reasonable scan duration
            await r.set(
                f"scan_live_state:{self.scan_id}",
                json.dumps(self._live_state),
                ex=86400,
            )
            logger.debug("Emitted event %s on %s", event, self.channel)
        except Exception:
            logger.warning("Failed to emit event %s for scan %d", event, self.scan_id, exc_info=True)

        # Persist tool statuses to DB on every tool status transition so that
        # the REST API (/scans/{id}) always reflects current live state.
        # This is the reliable path: works even if Redis snapshot is absent.
        if is_tool_status_event and self._db_session_factory is not None:
            try:
                await self._persist_tool_statuses_to_db()
            except Exception:
                logger.warning(
                    "Failed to persist tool statuses to DB for scan %d", self.scan_id, exc_info=True
                )

    def _update_live_state(self, event: str, data: dict[str, Any]) -> None:
        """Update the in-memory live state snapshot (persisted to Redis in emit)."""
        if event in self._TOOL_STATUS_EVENTS and "tool" in data:
            self._live_state["tool_statuses"][data["tool"]] = self._TOOL_STATUS_EVENTS[event]
        elif event == "phase_started":
            phase_num = data.get("phase_number", 0)
            self._live_state["current_phase"] = phase_num
            self._live_state["phase_statuses"][str(phase_num)] = "running"
        elif event == "phase_completed":
            phase_num = data.get("phase_number", 0)
            self._live_state["phase_statuses"][str(phase_num)] = "completed"
        elif event == "phase_failed":
            phase_num = data.get("phase_number", 0)
            self._live_state["phase_statuses"][str(phase_num)] = "failed"
        elif event == "tool_log":
            ts = int(datetime.now(timezone.utc).timestamp() * 1000)
            logs: list = self._live_state["logs"]
            logs.append({
                "tool": data.get("tool", ""),
                "line": data.get("line", ""),
                "timestamp": ts,
            })
            # Keep only the most recent 200 lines to bound Redis key size
            if len(logs) > 200:
                self._live_state["logs"] = logs[-200:]

    async def _persist_tool_statuses_to_db(self) -> None:
        """Write current tool_statuses to the running phase's DB record.

        Called on every tool status event so the REST API is always up-to-date.
        Without this, tool_statuses would only be written at phase completion,
        leaving the running phase with an empty dict while it executes.
        """
        if self._db_session_factory is None:
            return
        async with self._db_session_factory() as session:
            result = await session.execute(
                select(ScanPhase).where(
                    ScanPhase.scan_id == self.scan_id,
                    ScanPhase.status == PhaseStatus.RUNNING,
                )
            )
            phase = result.scalar_one_or_none()
            if phase is not None:
                phase.tool_statuses = dict(self.tool_statuses)
                await session.commit()

    async def close(self) -> None:
        """Close the underlying Redis connection."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


class PipelineEngine:
    """Orchestrates the 4-phase scan pipeline.

    Lifecycle:
        1. ``__init__`` — Create DockerManager, EventEmitter
        2. ``run()`` — Execute all phases sequentially
        3. ``close()`` — Tear down resources

    The engine checks for cancellation between phases by reading a
    Redis key ``scan_cancel:{scan_id}``.
    """

    def __init__(self, scan_id: int, db_session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.scan_id = scan_id
        self.db_session_factory = db_session_factory
        self.docker = DockerManager()
        self.emitter = EventEmitter(scan_id, db_session_factory=db_session_factory)
        self._cancel_redis: aioredis.Redis | None = None

    # ── Main entry point ──────────────────────────────────────────────

    async def run(self) -> None:
        """Execute the full pipeline: recon -> network -> vulnscan -> report.

        Error handling strategy:
        - Each phase is wrapped in granular exception handling.
        - ``ToolExecutionError`` is logged with tool context.
        - ``asyncio.CancelledError`` is treated as a cancellation request.
        - A ``finally`` block ensures scan status is always set and
          resources are cleaned up regardless of how execution ends.
        - The ``scan_failed`` event includes the phase that failed,
          the exception class, and a truncated traceback.
        """
        import traceback

        from app.core.exceptions import ToolExecutionError
        from app.pipeline.phase_network import run_phase_network
        from app.pipeline.phase_recon import run_phase_recon
        from app.pipeline.phase_report import run_phase_report
        from app.pipeline.phase_vulnscan import run_phase_vulnscan
        from app.pipeline.utils import ToolTimeout

        phase_funcs: dict[str, Callable[..., Coroutine]] = {
            "recon": run_phase_recon,
            "network": run_phase_network,
            "vulnscan": run_phase_vulnscan,
            "report": run_phase_report,
        }

        scan = await self._load_scan()
        if scan is None:
            logger.error("Scan %d not found in database — aborting", self.scan_id)
            return

        config = scan.config or {}
        results_dir = scan.results_dir
        target_domain = scan.target_domain

        scan_completed = False
        scan_failed = False
        failure_error: str | None = None

        try:
            # Update scan to RUNNING
            await self._update_scan_status(ScanStatus.RUNNING)
            await self.emitter.emit("scan_started", {
                "scan_id": self.scan_id,
                "target_domain": target_domain,
            })

            for phase_number, phase_name in PHASES:
                # Check cancellation before each phase
                if await self._is_cancelled():
                    logger.info("Scan %d cancelled before phase %d (%s)", self.scan_id, phase_number, phase_name)
                    await self._update_scan_status(ScanStatus.CANCELLED)
                    await self.emitter.emit("scan_cancelled", {"scan_id": self.scan_id})
                    return

                phase_func = phase_funcs[phase_name]
                phase_record = await self._start_phase(phase_number, phase_name)

                try:
                    await self.emitter.emit("phase_started", {
                        "phase_number": phase_number,
                        "phase_name": phase_name,
                    })

                    # Each phase function receives the same standard arguments
                    await phase_func(
                        docker=self.docker,
                        config=config,
                        results_dir=results_dir,
                        emitter=self.emitter,
                        db_session_factory=self.db_session_factory,
                        scan_id=self.scan_id,
                    )

                    await self._complete_phase(phase_record, self.emitter.tool_statuses)
                    self.emitter.reset_tool_statuses()
                    await self.emitter.emit("phase_completed", {
                        "phase_number": phase_number,
                        "phase_name": phase_name,
                        "duration_seconds": phase_record.duration_seconds,
                    })

                except asyncio.CancelledError:
                    logger.info("Scan %d cancelled during phase %d (%s)", self.scan_id, phase_number, phase_name)
                    await self._fail_phase(phase_record, "Cancelled")
                    await self._update_scan_status(ScanStatus.CANCELLED)
                    await self.emitter.emit("scan_cancelled", {
                        "scan_id": self.scan_id,
                        "phase": phase_name,
                    })
                    return

                except ToolExecutionError as exc:
                    tb = traceback.format_exc()
                    logger.error(
                        "ToolExecutionError in phase %d (%s) for scan %d — tool=%s exit=%d: %s",
                        phase_number,
                        phase_name,
                        self.scan_id,
                        exc.tool,
                        exc.exit_code,
                        str(exc),
                    )
                    await self._fail_phase(phase_record, str(exc))
                    await self.emitter.emit("phase_failed", {
                        "phase_number": phase_number,
                        "phase_name": phase_name,
                        "error": str(exc)[:500],
                        "tool": exc.tool,
                        "exit_code": exc.exit_code,
                    })

                    if phase_name == "report":
                        logger.warning("Report phase failed but scan continues as completed")
                        continue

                    scan_failed = True
                    failure_error = str(exc)
                    await self._update_scan_status(ScanStatus.FAILED, error=failure_error)
                    await self.emitter.emit("scan_failed", {
                        "scan_id": self.scan_id,
                        "error": failure_error[:500],
                        "phase": phase_name,
                        "phase_number": phase_number,
                        "exception_type": type(exc).__name__,
                        "tool": exc.tool,
                        "traceback": tb[-1000:],
                    })
                    return

                except ToolTimeout as exc:
                    logger.error(
                        "Timeout in phase %d (%s) for scan %d — tool=%s timeout=%ds",
                        phase_number,
                        phase_name,
                        self.scan_id,
                        exc.tool,
                        exc.timeout_seconds,
                    )
                    await self._fail_phase(phase_record, str(exc))
                    await self.emitter.emit("phase_failed", {
                        "phase_number": phase_number,
                        "phase_name": phase_name,
                        "error": str(exc)[:500],
                        "tool": exc.tool,
                        "timeout_seconds": exc.timeout_seconds,
                    })

                    if phase_name == "report":
                        logger.warning("Report phase timed out but scan continues as completed")
                        continue

                    scan_failed = True
                    failure_error = str(exc)
                    await self._update_scan_status(ScanStatus.FAILED, error=failure_error)
                    await self.emitter.emit("scan_failed", {
                        "scan_id": self.scan_id,
                        "error": failure_error[:500],
                        "phase": phase_name,
                        "phase_number": phase_number,
                        "exception_type": "ToolTimeout",
                    })
                    return

                except Exception as exc:
                    tb = traceback.format_exc()
                    logger.exception(
                        "Unexpected error in phase %d (%s) for scan %d",
                        phase_number,
                        phase_name,
                        self.scan_id,
                    )
                    await self._fail_phase(phase_record, str(exc))
                    await self.emitter.emit("phase_failed", {
                        "phase_number": phase_number,
                        "phase_name": phase_name,
                        "error": str(exc)[:500],
                    })

                    # Report phase failure is non-fatal; other phase failures are fatal
                    if phase_name == "report":
                        logger.warning("Report phase failed but scan continues as completed")
                        continue

                    scan_failed = True
                    failure_error = str(exc)
                    await self._update_scan_status(ScanStatus.FAILED, error=failure_error)
                    await self.emitter.emit("scan_failed", {
                        "scan_id": self.scan_id,
                        "error": failure_error[:500],
                        "phase": phase_name,
                        "phase_number": phase_number,
                        "exception_type": type(exc).__name__,
                        "traceback": tb[-1000:],
                    })
                    return

            # All phases completed successfully
            scan_completed = True
            summary = await self._build_summary()
            await self._update_scan_status(ScanStatus.COMPLETED)
            await self.emitter.emit("pipeline_complete", summary)

        except Exception as exc:
            # Catch-all for unexpected errors outside the phase loop
            # (e.g. failure in _load_scan, _update_scan_status, etc.)
            logger.exception("Fatal error in pipeline engine for scan %d", self.scan_id)
            if not scan_failed:
                failure_error = f"Pipeline engine error: {exc}"
                try:
                    await self._update_scan_status(ScanStatus.FAILED, error=failure_error)
                    await self.emitter.emit("scan_failed", {
                        "scan_id": self.scan_id,
                        "error": failure_error[:500],
                        "exception_type": type(exc).__name__,
                    })
                except Exception:
                    logger.error("Failed to update scan status after fatal error for scan %d", self.scan_id)

        finally:
            # Ensure cleanup always happens regardless of how we exit
            logger.info(
                "Pipeline engine finishing for scan %d — completed=%s, failed=%s",
                self.scan_id,
                scan_completed,
                scan_failed,
            )
            await self._cleanup()

    # ── Scan helpers ──────────────────────────────────────────────────

    async def _load_scan(self) -> Scan | None:
        """Load the scan record from the database."""
        async with self.db_session_factory() as session:
            result = await session.execute(select(Scan).where(Scan.id == self.scan_id))
            return result.scalar_one_or_none()

    async def _update_scan_status(
        self,
        status: ScanStatus,
        error: str | None = None,
    ) -> None:
        """Update the scan's status, timestamps, and optional error message."""
        async with self.db_session_factory() as session:
            result = await session.execute(select(Scan).where(Scan.id == self.scan_id))
            scan = result.scalar_one_or_none()
            if scan is None:
                return
            scan.status = status
            if status == ScanStatus.RUNNING and scan.started_at is None:
                scan.started_at = datetime.now(timezone.utc)
            if status in (ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED):
                scan.completed_at = datetime.now(timezone.utc)
            if error:
                scan.error_message = error[:2000]
            await session.commit()

    async def _is_cancelled(self) -> bool:
        """Check the Redis cancellation flag for this scan."""
        try:
            if self._cancel_redis is None:
                self._cancel_redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            val = await self._cancel_redis.get(f"scan_cancel:{self.scan_id}")
            return val is not None
        except Exception:
            logger.warning("Failed to check cancellation flag for scan %d", self.scan_id, exc_info=True)
            return False

    # ── Phase helpers ─────────────────────────────────────────────────

    async def _start_phase(self, phase_number: int, phase_name: str) -> ScanPhase:
        """Create or update the ScanPhase record to RUNNING."""
        async with self.db_session_factory() as session:
            # Check for existing phase record (created at scan creation time)
            result = await session.execute(
                select(ScanPhase).where(
                    ScanPhase.scan_id == self.scan_id,
                    ScanPhase.phase_number == phase_number,
                )
            )
            phase_record = result.scalar_one_or_none()

            if phase_record is None:
                phase_record = ScanPhase(
                    scan_id=self.scan_id,
                    phase_number=phase_number,
                    phase_name=phase_name,
                    status=PhaseStatus.RUNNING,
                    started_at=datetime.now(timezone.utc),
                )
                session.add(phase_record)
            else:
                phase_record.status = PhaseStatus.RUNNING
                phase_record.started_at = datetime.now(timezone.utc)

            # Also update the scan's current_phase field
            scan_result = await session.execute(select(Scan).where(Scan.id == self.scan_id))
            scan = scan_result.scalar_one_or_none()
            if scan is not None:
                scan.current_phase = phase_number

            await session.commit()
            await session.refresh(phase_record)
            return phase_record

    async def _complete_phase(
        self, phase_record: ScanPhase, tool_statuses: dict[str, str] | None = None
    ) -> None:
        """Mark a phase as completed and persist tool statuses."""
        async with self.db_session_factory() as session:
            result = await session.execute(
                select(ScanPhase).where(ScanPhase.id == phase_record.id)
            )
            phase = result.scalar_one_or_none()
            if phase is None:
                return
            phase.status = PhaseStatus.COMPLETED
            phase.completed_at = datetime.now(timezone.utc)
            if phase.started_at:
                delta = phase.completed_at - phase.started_at
                phase.duration_seconds = delta.total_seconds()
            if tool_statuses:
                phase.tool_statuses = tool_statuses
            await session.commit()
            # Update in-memory record for the event
            phase_record.duration_seconds = phase.duration_seconds

    async def _fail_phase(self, phase_record: ScanPhase, error: str) -> None:
        """Mark a phase as failed."""
        async with self.db_session_factory() as session:
            result = await session.execute(
                select(ScanPhase).where(ScanPhase.id == phase_record.id)
            )
            phase = result.scalar_one_or_none()
            if phase is None:
                return
            phase.status = PhaseStatus.FAILED
            phase.completed_at = datetime.now(timezone.utc)
            phase.error_message = error[:2000]
            if phase.started_at:
                delta = phase.completed_at - phase.started_at
                phase.duration_seconds = delta.total_seconds()
            await session.commit()

    # ── Summary ───────────────────────────────────────────────────────

    async def _build_summary(self) -> dict[str, Any]:
        """Build a summary dict of the entire scan for the pipeline_complete event."""
        from sqlalchemy import func as sqlfunc

        from app.models.finding import Finding
        from app.models.target import Target

        async with self.db_session_factory() as session:
            # Count targets
            target_count_result = await session.execute(
                select(sqlfunc.count(Target.id)).where(Target.scan_id == self.scan_id)
            )
            total_targets = target_count_result.scalar() or 0

            # Count findings by severity
            finding_rows = await session.execute(
                select(Finding.severity, sqlfunc.count(Finding.id))
                .where(Finding.scan_id == self.scan_id)
                .group_by(Finding.severity)
            )
            severity_counts: dict[str, int] = {}
            total_findings = 0
            for severity, count in finding_rows:
                severity_counts[severity.value if hasattr(severity, "value") else str(severity)] = count
                total_findings += count

            # Phase durations
            phase_rows = await session.execute(
                select(ScanPhase).where(ScanPhase.scan_id == self.scan_id).order_by(ScanPhase.phase_number)
            )
            phases_summary = []
            for phase in phase_rows.scalars():
                phases_summary.append({
                    "phase_number": phase.phase_number,
                    "phase_name": phase.phase_name,
                    "status": phase.status.value if hasattr(phase.status, "value") else str(phase.status),
                    "duration_seconds": phase.duration_seconds,
                })

        return {
            "scan_id": self.scan_id,
            "total_targets": total_targets,
            "total_findings": total_findings,
            "severity_counts": severity_counts,
            "phases": phases_summary,
        }

    # ── Cleanup ─────────────────────────────────────────────────────────

    async def _cleanup(self) -> None:
        """Async cleanup of Redis connections and Docker client.

        Called in the ``finally`` block of ``run()`` to ensure resources
        are always released, even after unexpected errors.
        """
        try:
            await self.emitter.close()
        except Exception:
            logger.debug("Error closing event emitter for scan %d", self.scan_id, exc_info=True)

        try:
            if self._cancel_redis is not None:
                await self._cancel_redis.aclose()
                self._cancel_redis = None
        except Exception:
            logger.debug("Error closing cancel Redis for scan %d", self.scan_id, exc_info=True)

    # ── Lifecycle ─────────────────────────────────────────────────────

    def close(self) -> None:
        """Release all resources.  Call from a sync context after ``asyncio.run()``."""
        self.docker.close()
        # Redis connections will be cleaned up asynchronously via __del__,
        # but we attempt graceful closure here.
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._async_close())
            else:
                loop.run_until_complete(self._async_close())
        except RuntimeError:
            pass

    async def _async_close(self) -> None:
        """Async cleanup of Redis connections (legacy, for sync callers)."""
        await self._cleanup()
