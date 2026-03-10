"""Phase 4: Reporting — DefectDojo import, summary generation.

Pushes scan results to DefectDojo (if configured) and builds a final
summary of the entire scan.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.finding import Finding
from app.models.scan import Scan
from app.pipeline.engine import EventEmitter
from app.services.defectdojo_client import DefectDojoClient
from app.services.docker_manager import DockerManager

logger = logging.getLogger(__name__)


async def _push_to_defectdojo(
    scan: Scan,
    results_dir: str,
    emitter: EventEmitter,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Push scan results to DefectDojo.

    Creates a product (if needed), engagement, and imports available
    raw scan output files (Nuclei JSONL, ZAP JSON, Nmap XML).
    """
    if not settings.defectdojo_api_key:
        logger.info("DefectDojo API key not configured — skipping push")
        return

    await emitter.emit("tool_started", {"tool": "defectdojo"})

    client = DefectDojoClient(
        base_url=settings.defectdojo_url,
        api_key=settings.defectdojo_api_key,
    )

    try:
        # Get or create product for this domain
        product_id = await client.get_or_create_product(
            name=f"CyberSec - {scan.target_domain}",
        )

        # Create engagement for this scan
        engagement_id = await client.create_engagement(
            product_id=product_id,
            name=f"Scan {scan.scan_uid}",
        )

        logger.info("DefectDojo engagement %d created for scan %s", engagement_id, scan.scan_uid)

        # Import available scan results
        import_map: list[tuple[str, str, str]] = [
            # (file path relative to results_dir, DefectDojo scan type, filename)
            (f"{results_dir}/phase3_vulnscan/nuclei.jsonl", "Nuclei Scan", "nuclei.jsonl"),
            (f"{results_dir}/phase3_vulnscan/zap_report.json", "ZAP Scan", "zap_report.json"),
            (f"{results_dir}/phase2_network/nmap.xml", "Nmap Scan", "nmap.xml"),
        ]

        imported_count = 0
        for file_path, scan_type, filename in import_map:
            try:
                # Read the file from the shared volume via a container
                docker = DockerManager()
                try:
                    raw_content = await docker.read_file_from_container("theharvester", file_path)
                finally:
                    docker.close()

                if not raw_content.strip():
                    logger.info("Skipping empty file %s for DefectDojo import", file_path)
                    continue

                result = await client.import_scan(
                    engagement_id=engagement_id,
                    scan_type=scan_type,
                    file_content=raw_content.encode("utf-8"),
                    filename=filename,
                )
                imported_count += 1
                logger.info("Imported %s to DefectDojo: test_id=%s", filename, result.get("test"))

                # Update finding records with DefectDojo IDs if available
                dojo_test_id = result.get("test")
                if dojo_test_id:
                    tool_name = "nuclei" if "nuclei" in filename else ("zap" if "zap" in filename else "nmap")
                    async with db_session_factory() as session:
                        findings_result = await session.execute(
                            select(Finding).where(
                                Finding.scan_id == scan.id,
                                Finding.source_tool == tool_name,
                                Finding.defectdojo_id == None,  # noqa: E711
                            )
                        )
                        # We can't 1:1 map without DefectDojo finding IDs,
                        # so just note the test_id on a metadata level
                        for finding in findings_result.scalars():
                            finding.defectdojo_id = dojo_test_id
                        await session.commit()

            except Exception as exc:
                logger.warning("Failed to import %s to DefectDojo: %s", filename, exc)
                continue

        await emitter.emit("tool_completed", {"tool": "defectdojo"})
        await emitter.emit("tool_result", {
            "tool": "defectdojo",
            "imported_files": imported_count,
            "engagement_id": engagement_id,
        })

    except Exception as exc:
        logger.error("DefectDojo push failed: %s", exc)
        await emitter.emit("tool_error", {"tool": "defectdojo", "output": str(exc)[:500]})
        # Non-fatal — reporting failures should not fail the scan
    finally:
        await client.close()


async def _build_final_summary(
    scan_id: int,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, Any]:
    """Build a human-readable summary of the scan results."""
    from sqlalchemy import func as sqlfunc

    from app.models.base import Severity
    from app.models.target import Target

    async with db_session_factory() as session:
        # Target counts by type
        target_rows = await session.execute(
            select(Target.target_type, sqlfunc.count(Target.id))
            .where(Target.scan_id == scan_id)
            .group_by(Target.target_type)
        )
        target_counts: dict[str, int] = {}
        for target_type, count in target_rows:
            key = target_type.value if hasattr(target_type, "value") else str(target_type)
            target_counts[key] = count

        # Finding counts by severity
        finding_rows = await session.execute(
            select(Finding.severity, sqlfunc.count(Finding.id))
            .where(Finding.scan_id == scan_id)
            .group_by(Finding.severity)
        )
        severity_counts: dict[str, int] = {}
        total_findings = 0
        for severity, count in finding_rows:
            key = severity.value if hasattr(severity, "value") else str(severity)
            severity_counts[key] = count
            total_findings += count

        # Finding counts by tool
        tool_rows = await session.execute(
            select(Finding.source_tool, sqlfunc.count(Finding.id))
            .where(Finding.scan_id == scan_id)
            .group_by(Finding.source_tool)
        )
        tool_counts: dict[str, int] = {}
        for tool, count in tool_rows:
            tool_counts[tool] = count

        # Top findings (critical and high)
        top_findings_result = await session.execute(
            select(Finding)
            .where(
                Finding.scan_id == scan_id,
                Finding.severity.in_([Severity.CRITICAL, Severity.HIGH]),
            )
            .order_by(Finding.severity)
            .limit(20)
        )
        top_findings = [
            {
                "title": f.title,
                "severity": f.severity.value,
                "tool": f.source_tool,
                "url": f.affected_url,
            }
            for f in top_findings_result.scalars()
        ]

    return {
        "scan_id": scan_id,
        "target_counts": target_counts,
        "total_findings": total_findings,
        "severity_counts": severity_counts,
        "tool_counts": tool_counts,
        "top_findings": top_findings,
    }


# ── Phase orchestrator ────────────────────────────────────────────────


async def run_phase_report(
    docker: DockerManager,
    config: dict[str, Any],
    results_dir: str,
    emitter: EventEmitter,
    db_session_factory: async_sessionmaker[AsyncSession],
    scan_id: int,
) -> None:
    """Orchestrate Phase 4: Reporting.

    1. Push results to DefectDojo (if configured)
    2. Build final summary
    3. Emit summary event
    """
    # Load scan record
    async with db_session_factory() as session:
        result = await session.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()

    if scan is None:
        logger.error("Scan %d not found — cannot generate report", scan_id)
        return

    # Push to DefectDojo if configured
    push_to_dojo = config.get("push_to_defectdojo", True)
    if push_to_dojo:
        await _push_to_defectdojo(scan, results_dir, emitter, db_session_factory)

    # Build and emit summary
    summary = await _build_final_summary(scan_id, db_session_factory)
    await emitter.emit("tool_result", {
        "tool": "report",
        "summary": summary,
    })

    logger.info(
        "Phase 4 report complete: %d total findings, DefectDojo push=%s",
        summary["total_findings"],
        "enabled" if push_to_dojo else "disabled",
    )
