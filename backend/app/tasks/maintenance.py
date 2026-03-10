"""Maintenance Celery tasks.

Periodic tasks that can be scheduled via Celery Beat, such as
updating Nuclei templates.
"""

from __future__ import annotations

import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
def update_nuclei_templates(self) -> dict:
    """Update Nuclei vulnerability templates.

    Runs ``nuclei -update-templates`` inside the nuclei container.
    Can be scheduled via Celery Beat (e.g. daily).
    """
    logger.info("Starting Nuclei template update")
    try:
        result = asyncio.run(_do_update_nuclei_templates())
        return result
    except Exception as exc:
        logger.warning("Nuclei template update failed: %s — retrying", exc)
        raise self.retry(exc=exc)


async def _do_update_nuclei_templates() -> dict:
    """Execute the template update command inside the nuclei container."""
    from app.services.docker_manager import DockerManager

    docker = DockerManager()
    try:
        exit_code, output = await docker.exec_in_container(
            container="nuclei",
            command="nuclei -update-templates",
            timeout=300,
        )
        if exit_code != 0:
            logger.warning("Nuclei template update exited %d: %s", exit_code, output[-500:])
            return {"status": "warning", "exit_code": exit_code, "output": output[-500:]}

        logger.info("Nuclei templates updated successfully")
        return {"status": "success", "output": output[-500:]}
    finally:
        docker.close()
