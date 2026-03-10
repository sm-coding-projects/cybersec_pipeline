"""Phase 2: Network Scanning — Masscan, Nmap, httpx.

Masscan performs a fast port sweep, Nmap does deep service detection on
discovered ports, and httpx probes for live HTTP endpoints.  Results
enrich the existing targets in the database.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import ToolExecutionError
from app.models.base import TargetType
from app.models.target import Target
from app.pipeline.engine import EventEmitter
from app.pipeline.parsers import (
    HttpxResult,
    MasscanResult,
    NmapHost,
    parse_httpx_output,
    parse_masscan_output,
    parse_nmap_output,
)
from app.pipeline.utils import emit_tool_output, retry_tool_exec, validate_tool_output
from app.services.docker_manager import DockerManager

logger = logging.getLogger(__name__)


# ── Individual tool runners ───────────────────────────────────────────


async def run_masscan(
    docker: DockerManager,
    ips: list[str],
    config: dict[str, Any],
    results_dir: str,
    emitter: EventEmitter,
) -> list[MasscanResult]:
    """Run Masscan fast port sweep on the provided IP addresses.

    Command: ``masscan {ips} -p{ports} --rate={rate} -oJ {output_file}``
    """
    if not ips:
        logger.info("No IPs for Masscan — skipping")
        return []

    await emitter.emit("tool_started", {"tool": "masscan"})

    phase_dir = f"{results_dir}/phase2_network"
    output_file = f"{phase_dir}/masscan.json"
    rate = config.get("masscan_rate", 10000)
    ports = config.get("masscan_ports", "1-65535")

    await docker.exec_in_container("nmap-scanner", f"mkdir -p {phase_dir}")

    # Write targets to a file
    targets_file = f"{phase_dir}/masscan_targets.txt"
    ip_content = "\\n".join(ips)
    await docker.exec_in_container("nmap-scanner", f"printf '{ip_content}' > {targets_file}")

    command = f"masscan -iL {targets_file} -p{ports} --rate={rate} -oJ {output_file}"
    exit_code, output = await retry_tool_exec(
        docker=docker,
        container="nmap-scanner",
        command=command,
        max_retries=2,
        delay=5.0,
        timeout=600,
    )

    await emit_tool_output(emitter, "masscan", output)

    # Masscan exit code 1 can mean "no results" on some platforms — check output file
    if exit_code != 0:
        await emitter.emit("tool_error", {"tool": "masscan", "output": output[-500:]})
        logger.warning("Masscan exited %d: %s", exit_code, output[-200:])
        # Non-fatal: try to parse whatever output we got

    await emitter.emit("tool_completed", {"tool": "masscan"})

    # Validate output file
    await validate_tool_output(docker, "nmap-scanner", output_file, "masscan", required=False)

    # Read and parse
    try:
        raw_json = await docker.read_file_from_container("nmap-scanner", output_file)
    except ToolExecutionError:
        logger.warning("Could not read Masscan output from %s", output_file)
        return []

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        tmp.write(raw_json)
        tmp_path = tmp.name

    try:
        results = parse_masscan_output(tmp_path)
    finally:
        os.unlink(tmp_path)

    await emitter.emit("tool_result", {
        "tool": "masscan",
        "hosts": len(results),
        "total_ports": sum(len(r.ports) for r in results),
    })
    return results


async def run_nmap(
    docker: DockerManager,
    targets: list[MasscanResult] | list[str],
    config: dict[str, Any],
    results_dir: str,
    emitter: EventEmitter,
) -> list[NmapHost]:
    """Run Nmap service detection on discovered ports.

    If ``targets`` are ``MasscanResult`` objects, Nmap scans only those
    specific host:port pairs.  If they are plain IP strings, a default
    top-ports scan is performed.

    Command: ``nmap -sV -sC -oX {output_file} {target_spec}``
    """
    if not targets:
        logger.info("No targets for Nmap — skipping")
        return []

    await emitter.emit("tool_started", {"tool": "nmap"})

    phase_dir = f"{results_dir}/phase2_network"
    output_file = f"{phase_dir}/nmap.xml"

    await docker.exec_in_container("nmap-scanner", f"mkdir -p {phase_dir}")

    # Build target specification
    if targets and isinstance(targets[0], MasscanResult):
        # Build per-host port specs for targeted scanning
        nmap_targets: list[str] = []
        port_set: set[int] = set()
        for mr in targets:
            nmap_targets.append(mr.ip)
            port_set.update(mr.ports)

        if not port_set:
            logger.info("No open ports from Masscan — skipping Nmap")
            return []

        unique_ips = list(set(nmap_targets))
        port_arg = ",".join(str(p) for p in sorted(port_set))
        target_spec = f"-p {port_arg} {' '.join(unique_ips)}"
    else:
        # Plain IP strings — scan top ports
        target_spec = f"--top-ports 1000 {' '.join(str(t) for t in targets)}"

    nmap_scripts = config.get("nmap_scripts", "default,vuln")
    command = f"nmap -sV -sC --script={nmap_scripts} -oX {output_file} {target_spec}"
    exit_code, output = await retry_tool_exec(
        docker=docker,
        container="nmap-scanner",
        command=command,
        max_retries=2,
        delay=5.0,
        timeout=600,
    )

    await emit_tool_output(emitter, "nmap", output)

    if exit_code != 0:
        await emitter.emit("tool_error", {"tool": "nmap", "output": output[-500:]})
        raise ToolExecutionError(
            tool="nmap",
            message=f"Nmap failed: {output[-200:]}",
            exit_code=exit_code,
        )

    await emitter.emit("tool_completed", {"tool": "nmap"})

    # Validate output file
    await validate_tool_output(docker, "nmap-scanner", output_file, "nmap", required=False)

    # Read and parse XML output
    try:
        raw_xml = await docker.read_file_from_container("nmap-scanner", output_file)
    except ToolExecutionError:
        logger.warning("Could not read Nmap output from %s", output_file)
        return []

    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as tmp:
        tmp.write(raw_xml)
        tmp_path = tmp.name

    try:
        results = parse_nmap_output(tmp_path)
    finally:
        os.unlink(tmp_path)

    await emitter.emit("tool_result", {
        "tool": "nmap",
        "hosts": len(results),
        "total_ports": sum(len(h.ports) for h in results),
    })
    return results


async def run_httpx_scan(
    docker: DockerManager,
    subdomains: list[str],
    config: dict[str, Any],
    results_dir: str,
    emitter: EventEmitter,
) -> list[HttpxResult]:
    """Probe subdomains for live HTTP endpoints using httpx.

    Command: ``httpx -l {targets_file} -json -o {output_file} -silent -title -tech-detect -status-code``
    """
    if not subdomains:
        logger.info("No subdomains for httpx — skipping")
        return []

    await emitter.emit("tool_started", {"tool": "httpx"})

    phase_dir = f"{results_dir}/phase2_network"
    targets_file = f"{phase_dir}/httpx_targets.txt"
    output_file = f"{phase_dir}/httpx.json"

    await docker.exec_in_container("httpx", f"mkdir -p {phase_dir}")

    # Write targets
    subdomain_content = "\\n".join(subdomains)
    await docker.exec_in_container("httpx", f"printf '{subdomain_content}' > {targets_file}")

    command = f"httpx -l {targets_file} -json -o {output_file} -silent -title -tech-detect -status-code"
    exit_code, output = await retry_tool_exec(
        docker=docker,
        container="httpx",
        command=command,
        max_retries=2,
        delay=5.0,
        timeout=300,
    )

    await emit_tool_output(emitter, "httpx", output)

    if exit_code != 0:
        await emitter.emit("tool_error", {"tool": "httpx", "output": output[-500:]})
        logger.warning("httpx exited %d: %s", exit_code, output[-200:])
        # Non-fatal — some targets may have succeeded

    await emitter.emit("tool_completed", {"tool": "httpx"})

    # Validate output file
    await validate_tool_output(docker, "httpx", output_file, "httpx", required=False)

    # Read and parse
    try:
        raw_jsonl = await docker.read_file_from_container("httpx", output_file)
    except ToolExecutionError:
        logger.warning("Could not read httpx output from %s", output_file)
        return []

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        tmp.write(raw_jsonl)
        tmp_path = tmp.name

    try:
        results = parse_httpx_output(tmp_path)
    finally:
        os.unlink(tmp_path)

    await emitter.emit("tool_result", {
        "tool": "httpx",
        "endpoints": len(results),
    })
    return results


# ── Phase orchestrator ────────────────────────────────────────────────


async def run_phase_network(
    docker: DockerManager,
    config: dict[str, Any],
    results_dir: str,
    emitter: EventEmitter,
    db_session_factory: async_sessionmaker[AsyncSession],
    scan_id: int,
) -> None:
    """Orchestrate Phase 2: Network Scanning.

    1. Load live IPs and subdomains from Phase 1 targets in the DB
    2. Run Masscan (fast port sweep)
    3. Run Nmap (deep service scan on Masscan results)
    4. Run httpx (HTTP endpoint probing)
    5. Enrich targets in the database with open ports, HTTP status, etc.
    """
    # Load targets from Phase 1
    async with db_session_factory() as session:
        ip_result = await session.execute(
            select(Target).where(
                Target.scan_id == scan_id,
                Target.target_type == TargetType.IP,
            )
        )
        ip_targets = list(ip_result.scalars())
        ips = [t.value for t in ip_targets]

        subdomain_result = await session.execute(
            select(Target).where(
                Target.scan_id == scan_id,
                Target.target_type == TargetType.SUBDOMAIN,
                Target.is_live == True,  # noqa: E712
            )
        )
        subdomain_targets = list(subdomain_result.scalars())
        subdomains = [t.value for t in subdomain_targets]

        # Also include resolved IPs from subdomains
        for st in subdomain_targets:
            if st.resolved_ips:
                for ip in st.resolved_ips:
                    if ip not in ips:
                        ips.append(ip)

    logger.info("Phase 2 network scan: %d IPs, %d live subdomains", len(ips), len(subdomains))

    # Step 1: Masscan fast port sweep
    masscan_results: list[MasscanResult] = []
    if ips:
        try:
            masscan_results = await run_masscan(docker, ips, config, results_dir, emitter)
        except Exception as exc:
            logger.warning("Masscan failed: %s — continuing with top-ports Nmap", exc)
            await emitter.emit("tool_error", {"tool": "masscan", "error": str(exc)[:500]})

    # Step 2: Nmap service detection
    nmap_results: list[NmapHost] = []
    try:
        if masscan_results:
            nmap_results = await run_nmap(docker, masscan_results, config, results_dir, emitter)
        elif ips:
            # Masscan failed or found nothing — do a default Nmap scan
            nmap_results = await run_nmap(docker, ips, config, results_dir, emitter)
    except Exception as exc:
        logger.warning("Nmap failed: %s — continuing without service data", exc)
        await emitter.emit("tool_error", {"tool": "nmap", "error": str(exc)[:500]})

    # Step 3: httpx HTTP probing
    httpx_results: list[HttpxResult] = []
    try:
        httpx_results = await run_httpx_scan(docker, subdomains, config, results_dir, emitter)
    except Exception as exc:
        logger.warning("httpx failed: %s — continuing without HTTP data", exc)
        await emitter.emit("tool_error", {"tool": "httpx", "error": str(exc)[:500]})

    # Persist enrichment data to database
    async with db_session_factory() as session:
        # Enrich IP targets with open ports from Nmap
        nmap_by_ip: dict[str, NmapHost] = {h.ip: h for h in nmap_results}
        for ip in ips:
            if ip in nmap_by_ip:
                host = nmap_by_ip[ip]
                result = await session.execute(
                    select(Target).where(
                        Target.scan_id == scan_id,
                        Target.value == ip,
                        Target.target_type == TargetType.IP,
                    )
                )
                target = result.scalars().first()
                if target is not None:
                    target.open_ports = [
                        {"port": p.port, "protocol": p.protocol, "service": p.service, "version": p.version}
                        for p in host.ports
                        if p.state == "open"
                    ]

        # Enrich subdomains with httpx data
        httpx_by_host: dict[str, HttpxResult] = {}
        for hr in httpx_results:
            host_key = hr.host or hr.url
            httpx_by_host[host_key] = hr

        for subdomain in subdomains:
            httpx_data = httpx_by_host.get(subdomain)
            if httpx_data is None:
                # Try matching by URL prefix
                for key, val in httpx_by_host.items():
                    if subdomain in key:
                        httpx_data = val
                        break

            if httpx_data is not None:
                result = await session.execute(
                    select(Target).where(
                        Target.scan_id == scan_id,
                        Target.value == subdomain,
                        Target.target_type == TargetType.SUBDOMAIN,
                    )
                )
                target = result.scalars().first()
                if target is not None:
                    target.http_status = httpx_data.status_code
                    target.http_title = httpx_data.title[:500] if httpx_data.title else None
                    target.technologies = httpx_data.technologies if httpx_data.technologies else None

        # Save URL targets from httpx
        for hr in httpx_results:
            url_target = Target(
                scan_id=scan_id,
                target_type=TargetType.URL,
                value=hr.url,
                source_tool="httpx",
                is_live=True,
                http_status=hr.status_code,
                http_title=hr.title[:500] if hr.title else None,
                technologies=hr.technologies if hr.technologies else None,
            )
            session.add(url_target)

        await session.commit()

    logger.info(
        "Phase 2 network complete: %d masscan hosts, %d nmap hosts, %d httpx endpoints",
        len(masscan_results),
        len(nmap_results),
        len(httpx_results),
    )
