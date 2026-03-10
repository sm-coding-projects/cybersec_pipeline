"""Celery application instance and configuration.

Broker: Redis DB 0.  Result backend: Redis DB 1.
Task modules are auto-discovered from ``app.tasks.scan_tasks`` and
``app.tasks.maintenance``.
"""

from celery import Celery

from app.config import settings

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
