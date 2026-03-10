"""Celery application instance and configuration.

Broker: Redis DB 0.  Result backend: Redis DB 1.
Task modules are auto-discovered from ``app.tasks.scan_tasks`` and
``app.tasks.maintenance``.
"""

import asyncio
import logging

from celery import Celery
from celery.signals import worker_ready

from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "cybersec_pipeline",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    include=[
        "app.tasks.scan_tasks",
        "app.tasks.maintenance",
    ],
)


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    """Mark any scans still stuck in RUNNING/PENDING as FAILED on worker startup.

    When a worker is killed mid-scan (e.g. during a deployment), scans can be
    left in a zombie RUNNING state with no active pipeline. This handler runs
    once at startup and cleans them up so users can retry them.

    With Redis as the Celery broker, the default visibility timeout (1 hour)
    means tasks interrupted after that window are never requeued. This cleanup
    catches those cases.
    """
    try:
        asyncio.run(_cleanup_zombie_scans())
    except Exception:
        logger.exception("Worker startup cleanup failed — continuing anyway")


async def _cleanup_zombie_scans() -> None:
    """Async implementation of the zombie scan cleanup."""
    from datetime import datetime, timezone

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.models.base import PhaseStatus, ScanStatus
    from app.models.scan import Scan, ScanPhase

    db_engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=2)
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with session_factory() as session:
            result = await session.execute(
                select(Scan).where(Scan.status.in_([ScanStatus.RUNNING, ScanStatus.PENDING]))
            )
            zombie_scans = result.scalars().all()

            if not zombie_scans:
                logger.info("Worker startup: no zombie scans found")
                return

            now = datetime.now(timezone.utc)
            for scan in zombie_scans:
                scan.status = ScanStatus.FAILED
                scan.completed_at = now
                scan.error_message = (
                    "Pipeline interrupted: worker restarted while scan was in progress. "
                    "Click Retry to run again."
                )
                # Also mark any running phases as failed
                phase_result = await session.execute(
                    select(ScanPhase).where(
                        ScanPhase.scan_id == scan.id,
                        ScanPhase.status == PhaseStatus.RUNNING,
                    )
                )
                for phase in phase_result.scalars():
                    phase.status = PhaseStatus.FAILED
                    phase.completed_at = now
                    phase.error_message = "Interrupted by worker restart"

                logger.warning(
                    "Worker startup: marked zombie scan %d (%s) as FAILED",
                    scan.id,
                    scan.target_domain,
                )

            await session.commit()
            logger.info(
                "Worker startup: cleaned up %d zombie scan(s)", len(zombie_scans)
            )
    finally:
        await db_engine.dispose()
