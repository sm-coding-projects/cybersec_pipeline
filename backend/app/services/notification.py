"""Notification service for scan events.

Provides hooks for sending notifications (Slack, email, etc.) when scans
complete, fail, or discover critical findings.  Currently a stub that logs
events; integrations can be added later.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def notify_scan_completed(scan_id: int, target_domain: str, summary: dict[str, Any]) -> None:
    """Send a notification when a scan completes successfully."""
    logger.info(
        "Scan %d completed for %s: %d findings discovered",
        scan_id,
        target_domain,
        summary.get("total_findings", 0),
    )
    # TODO: Implement Slack webhook / email notification


async def notify_scan_failed(scan_id: int, target_domain: str, error: str) -> None:
    """Send a notification when a scan fails."""
    logger.warning(
        "Scan %d failed for %s: %s",
        scan_id,
        target_domain,
        error,
    )
    # TODO: Implement Slack webhook / email notification


async def notify_critical_finding(scan_id: int, finding_title: str, affected_host: str | None) -> None:
    """Send an immediate notification when a critical finding is discovered."""
    logger.info(
        "Critical finding in scan %d: %s (host: %s)",
        scan_id,
        finding_title,
        affected_host or "unknown",
    )
    # TODO: Implement Slack webhook / email notification
