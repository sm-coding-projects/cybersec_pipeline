"""Phase 3: Vulnerability Scanning — Nuclei, ZAP.

Nuclei and ZAP run in parallel on discovered web URLs.  Findings are
deduplicated and persisted to the database.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from typing import Any

import httpx

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import ToolExecutionError
from app.models.base import Severity, TargetType
from app.models.finding import Finding
from app.models.target import Target
from app.pipeline.engine import EventEmitter
from app.pipeline.parsers import NucleiFinding, ZapAlert, parse_nuclei_output, parse_zap_output
from app.pipeline.utils import emit_tool_output, retry_tool_exec, validate_tool_output
from app.services.docker_manager import DockerManager

logger = logging.getLogger(__name__)


# ── Severity mapping ──────────────────────────────────────────────────

ZAP_RISK_TO_SEVERITY: dict[str, Severity] = {
    "High": Severity.HIGH,
    "Medium": Severity.MEDIUM,
    "Low": Severity.LOW,
    "Informational": Severity.INFO,
    "Info": Severity.INFO,
}


# ── Individual tool runners ───────────────────────────────────────────


async def run_nuclei(
    docker: DockerManager,
    urls: list[str],
    config: dict[str, Any],
    results_dir: str,
    emitter: EventEmitter,
) -> list[NucleiFinding]:
    """Run Nuclei vulnerability scanner against the provided URLs.

    Command: ``nuclei -l {targets_file} -jsonl -o {output_file} -severity {severities} -rate-limit {rate}``
    """
    if not urls:
        logger.info("No URLs for Nuclei — skipping")
        return []

    await emitter.emit("tool_started", {"tool": "nuclei"})

    phase_dir = f"{results_dir}/phase3_vulnscan"
    targets_file = f"{phase_dir}/nuclei_targets.txt"
    output_file = f"{phase_dir}/nuclei.jsonl"
    rate_limit = config.get("nuclei_rate_limit", 150)
    severities = config.get("nuclei_severities", "critical,high,medium,low,info")

    await docker.exec_in_container("nuclei", f"mkdir -p {phase_dir}")

    # Write URL targets
    url_content = "\\n".join(urls)
    await docker.exec_in_container("nuclei", f"printf '{url_content}' > {targets_file}")

    command = (
        f"nuclei -l {targets_file} -jsonl -o {output_file} "
        f"-severity {severities} -rate-limit {rate_limit} -silent"
    )
    exit_code, output = await retry_tool_exec(
        docker=docker,
        container="nuclei",
        command=command,
        max_retries=2,
        delay=5.0,
        timeout=1800,  # Nuclei can take a long time
    )

    await emit_tool_output(emitter, "nuclei", output)

    if exit_code != 0:
        await emitter.emit("tool_error", {"tool": "nuclei", "output": output[-500:]})
        logger.warning("Nuclei exited %d: %s", exit_code, output[-200:])
        # Non-fatal — try to parse partial results

    await emitter.emit("tool_completed", {"tool": "nuclei"})

    # Validate output file
    await validate_tool_output(docker, "nuclei", output_file, "nuclei", required=False)

    # Read and parse JSONL output
    try:
        raw_jsonl = await docker.read_file_from_container("nuclei", output_file)
    except ToolExecutionError:
        logger.warning("Could not read Nuclei output from %s", output_file)
        return []

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
        tmp.write(raw_jsonl)
        tmp_path = tmp.name

    try:
        findings = parse_nuclei_output(tmp_path)
    finally:
        os.unlink(tmp_path)

    # Emit finding_discovered events for high+ severity
    for f in findings:
        if f.severity in (Severity.CRITICAL, Severity.HIGH):
            await emitter.emit("finding_discovered", {
                "title": f.name,
                "severity": f.severity.value,
                "tool": "nuclei",
                "url": f.matched_at,
            })

    await emitter.emit("tool_result", {
        "tool": "nuclei",
        "findings": len(findings),
    })
    return findings


async def run_zap(
    urls: list[str],
    config: dict[str, Any],
    results_dir: str,
    emitter: EventEmitter,
) -> list[ZapAlert]:
    """Run ZAP active/passive scan via ZAP's REST API.

    ZAP is accessed via its REST API at http://zap:8090, not via docker exec.
    Flow: create context -> spider -> active scan -> get alerts -> export report.
    """
    if not urls:
        logger.info("No URLs for ZAP — skipping")
        return []

    await emitter.emit("tool_started", {"tool": "zap"})

    zap_base_url = config.get("zap_api_url", "http://zap:8090")
    zap_api_key = config.get("zap_api_key", "")

    params: dict[str, str] = {}
    if zap_api_key:
        params["apikey"] = zap_api_key

    try:
        async with httpx.AsyncClient(base_url=zap_base_url, timeout=30.0) as client:
            # Verify ZAP is reachable
            try:
                version_resp = await client.get("/JSON/core/view/version/", params=params)
                version_resp.raise_for_status()
                logger.info("ZAP version: %s", version_resp.json().get("version", "unknown"))
            except Exception as exc:
                await emitter.emit("tool_error", {"tool": "zap", "output": f"ZAP not reachable: {exc}"})
                raise ToolExecutionError(tool="zap", message=f"ZAP API not reachable: {exc}")

            # Spider each URL (limited depth for speed)
            for url in urls[:10]:  # Limit to avoid extremely long scans
                try:
                    await emitter.emit("tool_log", {"tool": "zap", "line": f"Starting spider: {url}"})
                    spider_params = {**params, "url": url, "maxChildren": "10", "recurse": "true"}
                    spider_resp = await client.get("/JSON/spider/action/scan/", params=spider_params)
                    spider_resp.raise_for_status()
                    spider_id = spider_resp.json().get("scan", "0")

                    # Wait for spider to complete (poll with timeout)
                    for poll in range(60):  # Max 5 minutes per URL
                        status_resp = await client.get(
                            "/JSON/spider/view/status/",
                            params={**params, "scanId": str(spider_id)},
                        )
                        progress = status_resp.json().get("status", "0")
                        if progress == "100":
                            await emitter.emit("tool_log", {"tool": "zap", "line": f"Spider complete: {url}"})
                            break
                        if poll % 6 == 0:  # Log every 30s
                            await emitter.emit("tool_log", {"tool": "zap", "line": f"Spider {progress}% for {url}"})
                        await asyncio.sleep(5)

                except Exception as exc:
                    logger.warning("ZAP spider failed for %s: %s", url, exc)
                    continue

            # Run active scan on each URL
            for url in urls[:10]:
                try:
                    await emitter.emit("tool_log", {"tool": "zap", "line": f"Starting active scan: {url}"})
                    ascan_params = {**params, "url": url, "recurse": "true"}
                    ascan_resp = await client.get("/JSON/ascan/action/scan/", params=ascan_params)
                    ascan_resp.raise_for_status()
                    scan_id = ascan_resp.json().get("scan", "0")

                    # Wait for active scan to complete
                    for poll in range(120):  # Max 10 minutes per URL
                        status_resp = await client.get(
                            "/JSON/ascan/view/status/",
                            params={**params, "scanId": str(scan_id)},
                        )
                        progress = status_resp.json().get("status", "0")
                        if progress == "100":
                            await emitter.emit("tool_log", {"tool": "zap", "line": f"Active scan complete: {url}"})
                            break
                        if poll % 6 == 0:  # Log every 30s
                            await emitter.emit("tool_log", {"tool": "zap", "line": f"Active scan {progress}% for {url}"})
                        await asyncio.sleep(5)

                except Exception as exc:
                    logger.warning("ZAP active scan failed for %s: %s", url, exc)
                    continue

            # Retrieve alerts
            try:
                alerts_resp = await client.get(
                    "/JSON/core/view/alerts/",
                    params={**params, "start": "0", "count": "1000"},
                )
                alerts_resp.raise_for_status()
                alerts_data = alerts_resp.json()
            except Exception as exc:
                logger.warning("Could not retrieve ZAP alerts: %s", exc)
                alerts_data = {"alerts": []}

            # Generate JSON report and save to results volume
            phase_dir = f"{results_dir}/phase3_vulnscan"
            report_file = f"{phase_dir}/zap_report.json"

            try:
                report_resp = await client.get(
                    "/OTHER/core/other/jsonreport/",
                    params=params,
                )
                report_resp.raise_for_status()
                report_content = report_resp.text
            except Exception as exc:
                logger.warning("Could not generate ZAP JSON report: %s", exc)
                # Fall back to constructing from alerts
                report_content = json.dumps({"site": [{"alerts": alerts_data.get("alerts", [])}]})

    except ToolExecutionError:
        raise
    except Exception as exc:
        await emitter.emit("tool_error", {"tool": "zap", "output": str(exc)[:500]})
        raise ToolExecutionError(tool="zap", message=f"ZAP scan failed: {exc}")

    await emitter.emit("tool_completed", {"tool": "zap"})

    # Parse the report
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        tmp.write(report_content)
        tmp_path = tmp.name

    try:
        zap_alerts = parse_zap_output(tmp_path)
    finally:
        os.unlink(tmp_path)

    # Emit finding_discovered events for high+ alerts
    for alert in zap_alerts:
        if alert.risk in ("High", "Critical"):
            await emitter.emit("finding_discovered", {
                "title": alert.alert,
                "severity": alert.risk.lower(),
                "tool": "zap",
                "url": alert.url,
            })

    await emitter.emit("tool_result", {
        "tool": "zap",
        "findings": len(zap_alerts),
    })
    return zap_alerts


# ── Phase orchestrator ────────────────────────────────────────────────


async def run_phase_vulnscan(
    docker: DockerManager,
    config: dict[str, Any],
    results_dir: str,
    emitter: EventEmitter,
    db_session_factory: async_sessionmaker[AsyncSession],
    scan_id: int,
) -> None:
    """Orchestrate Phase 3: Vulnerability Scanning.

    1. Load web URLs from Phase 2 targets in the DB
    2. Run Nuclei + ZAP in parallel (asyncio.gather, return_exceptions=True)
    3. Save findings to the database
    """
    # Load URL targets from DB
    async with db_session_factory() as session:
        url_result = await session.execute(
            select(Target).where(
                Target.scan_id == scan_id,
                Target.target_type == TargetType.URL,
                Target.is_live == True,  # noqa: E712
            )
        )
        url_targets = list(url_result.scalars())
        urls = [t.value for t in url_targets]

    if not urls:
        logger.info("No live URLs for vulnerability scanning — phase will have no findings")
        return

    logger.info("Phase 3 vulnscan: scanning %d URLs", len(urls))

    # Build tasks
    tasks = [run_nuclei(docker, urls, config, results_dir, emitter)]

    enable_zap = config.get("enable_zap", True)
    if enable_zap:
        tasks.append(run_zap(urls, config, results_dir, emitter))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    nuclei_findings: list[NucleiFinding] = []
    zap_alerts: list[ZapAlert] = []

    # Result 0 is always Nuclei
    if isinstance(results[0], Exception):
        logger.warning("Nuclei failed: %s", results[0])
        await emitter.emit("tool_error", {"tool": "nuclei", "error": str(results[0])[:500]})
    else:
        nuclei_findings = results[0]

    # Result 1 is ZAP (if enabled)
    if enable_zap and len(results) > 1:
        if isinstance(results[1], Exception):
            logger.warning("ZAP failed: %s", results[1])
            await emitter.emit("tool_error", {"tool": "zap", "error": str(results[1])[:500]})
        else:
            zap_alerts = results[1]

    # Build a URL-to-target-id lookup for linking findings to targets
    async with db_session_factory() as session:
        url_result = await session.execute(
            select(Target).where(
                Target.scan_id == scan_id,
                Target.target_type == TargetType.URL,
            )
        )
        target_lookup: dict[str, int] = {}
        for t in url_result.scalars():
            target_lookup[t.value] = t.id

    # Save findings to DB
    async with db_session_factory() as session:
        # Nuclei findings
        for nf in nuclei_findings:
            # Try to match target
            target_id = target_lookup.get(nf.matched_at) or target_lookup.get(nf.url or "")

            finding = Finding(
                scan_id=scan_id,
                target_id=target_id,
                title=nf.name[:500],
                severity=nf.severity,
                source_tool="nuclei",
                template_id=nf.template_id,
                description=nf.description[:5000] if nf.description else "",
                evidence=nf.matched_at,
                remediation=None,
                reference_urls=nf.reference,
                affected_url=nf.matched_at[:1000] if nf.matched_at else None,
                affected_host=nf.host[:255] if nf.host else None,
            )
            session.add(finding)

        # ZAP findings
        for za in zap_alerts:
            severity = ZAP_RISK_TO_SEVERITY.get(za.risk, Severity.INFO)
            target_id = target_lookup.get(za.url)

            finding = Finding(
                scan_id=scan_id,
                target_id=target_id,
                title=za.alert[:500],
                severity=severity,
                source_tool="zap",
                description=za.description[:5000] if za.description else "",
                remediation=za.solution[:5000] if za.solution else None,
                reference_urls=[za.reference] if za.reference else [],
                affected_url=za.url[:1000] if za.url else None,
            )
            session.add(finding)

        await session.commit()

    logger.info(
        "Phase 3 vulnscan complete: %d nuclei findings, %d zap alerts",
        len(nuclei_findings),
        len(zap_alerts),
    )
