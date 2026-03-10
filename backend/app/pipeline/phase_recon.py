"""Phase 1: Reconnaissance — theHarvester, Amass, dnsx.

theHarvester and Amass run in parallel for subdomain enumeration and
IP discovery.  Results are merged, deduplicated, then passed to dnsx
for DNS resolution.  Discovered targets are persisted to the database.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import ToolExecutionError
from app.models.base import TargetType
from app.models.target import Target
from app.pipeline.engine import EventEmitter
from app.pipeline.parsers import AmassResult, HarvesterResult, parse_amass_output, parse_harvester_output
from app.pipeline.utils import emit_tool_output, retry_tool_exec, validate_tool_output
from app.services.docker_manager import DockerManager

logger = logging.getLogger(__name__)


# ── Individual tool runners ───────────────────────────────────────────


async def run_theharvester(
    docker: DockerManager,
    config: dict[str, Any],
    results_dir: str,
    emitter: EventEmitter,
) -> HarvesterResult:
    """Run theHarvester and return parsed results.

    Command: ``theHarvester -d {domain} -b {sources} -f {output_file}``
    Output: JSON file at ``{results_dir}/phase1_recon/theharvester.json``
    """
    await emitter.emit("tool_started", {"tool": "theharvester"})

    domain = config["target_domain"]
    sources = config.get("harvester_sources", "bing,crtsh,dnsdumpster")
    phase_dir = f"{results_dir}/phase1_recon"
    output_file = f"{phase_dir}/theharvester"

    # Ensure output directory exists
    await docker.exec_in_container("theharvester", f"mkdir -p {phase_dir}")

    command = f"theHarvester -d {domain} -b {sources} -f {output_file}"
    exit_code, output = await retry_tool_exec(
        docker=docker,
        container="theharvester",
        command=command,
        max_retries=2,
        delay=5.0,
        timeout=300,
    )

    await emit_tool_output(emitter, "theharvester", output)

    if exit_code != 0:
        await emitter.emit("tool_error", {"tool": "theharvester", "output": output[-500:]})
        raise ToolExecutionError(
            tool="theharvester",
            message=f"theHarvester failed: {output[-200:]}",
            exit_code=exit_code,
        )

    await emitter.emit("tool_completed", {"tool": "theharvester"})

    # Parse output — theHarvester appends .json to the filename
    json_path = f"{output_file}.json"

    # Validate output file exists
    await validate_tool_output(docker, "theharvester", json_path, "theharvester", required=False)
    try:
        raw_json = await docker.read_file_from_container("theharvester", json_path)
    except ToolExecutionError:
        # Fall back to the exact path (some versions don't append .json)
        try:
            raw_json = await docker.read_file_from_container("theharvester", output_file)
        except ToolExecutionError:
            logger.warning("Could not read theHarvester output from %s or %s", json_path, output_file)
            return HarvesterResult()

    # Write to a temp local-style path and parse
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        tmp.write(raw_json)
        tmp_path = tmp.name

    try:
        result = parse_harvester_output(tmp_path)
    finally:
        os.unlink(tmp_path)

    await emitter.emit("tool_result", {
        "tool": "theharvester",
        "subdomains": len(result.subdomains),
        "ips": len(result.ips),
        "emails": len(result.emails),
    })
    return result


async def run_amass(
    docker: DockerManager,
    config: dict[str, Any],
    results_dir: str,
    emitter: EventEmitter,
) -> AmassResult:
    """Run Amass passive enumeration and return parsed results.

    Command: ``amass enum -d {domain} -timeout {timeout} -json {output_file}``
    Output: JSONL file at ``{results_dir}/phase1_recon/amass.json``
    """
    await emitter.emit("tool_started", {"tool": "amass"})

    domain = config["target_domain"]
    timeout = config.get("amass_timeout", 15)
    phase_dir = f"{results_dir}/phase1_recon"
    output_file = f"{phase_dir}/amass.json"

    await docker.exec_in_container("amass", f"mkdir -p {phase_dir}")

    command = f"amass enum -passive -d {domain} -timeout {timeout} -json {output_file}"
    exit_code, output = await retry_tool_exec(
        docker=docker,
        container="amass",
        command=command,
        max_retries=2,
        delay=5.0,
        timeout=timeout * 60 + 60,  # Extra buffer beyond the tool timeout
    )

    await emit_tool_output(emitter, "amass", output)

    if exit_code != 0:
        await emitter.emit("tool_error", {"tool": "amass", "output": output[-500:]})
        raise ToolExecutionError(
            tool="amass",
            message=f"Amass failed: {output[-200:]}",
            exit_code=exit_code,
        )

    await emitter.emit("tool_completed", {"tool": "amass"})

    # Validate output file exists
    await validate_tool_output(docker, "amass", output_file, "amass", required=False)

    # Read and parse output
    try:
        raw_jsonl = await docker.read_file_from_container("amass", output_file)
    except ToolExecutionError:
        logger.warning("Could not read Amass output from %s", output_file)
        return AmassResult()

    import tempfile
    import os

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        tmp.write(raw_jsonl)
        tmp_path = tmp.name

    try:
        result = parse_amass_output(tmp_path)
    finally:
        os.unlink(tmp_path)

    await emitter.emit("tool_result", {
        "tool": "amass",
        "subdomains": len(result.subdomains),
        "ips": len(result.ips),
    })
    return result


async def run_dnsx(
    docker: DockerManager,
    subdomains: list[str],
    results_dir: str,
    emitter: EventEmitter,
) -> dict[str, list[str]]:
    """Resolve subdomains to IPs using dnsx.

    Writes subdomains to a file, pipes them to dnsx, and returns a mapping
    of ``{subdomain: [resolved_ips]}``.
    """
    if not subdomains:
        logger.info("No subdomains to resolve via dnsx")
        return {}

    await emitter.emit("tool_started", {"tool": "dnsx"})

    phase_dir = f"{results_dir}/phase1_recon"
    targets_file = f"{phase_dir}/subdomains.txt"
    output_file = f"{phase_dir}/dnsx_output.json"

    await docker.exec_in_container("dnsx", f"mkdir -p {phase_dir}")

    # Write subdomain list to file inside the container
    subdomain_content = "\\n".join(subdomains)
    await docker.exec_in_container("dnsx", f"printf '{subdomain_content}' > {targets_file}")

    # Run dnsx with JSON output for resolution data
    command = f"dnsx -l {targets_file} -json -o {output_file} -resp -a -silent"
    exit_code, output = await retry_tool_exec(
        docker=docker,
        container="dnsx",
        command=command,
        max_retries=2,
        delay=5.0,
        timeout=300,
    )

    await emit_tool_output(emitter, "dnsx", output)

    if exit_code != 0:
        await emitter.emit("tool_error", {"tool": "dnsx", "output": output[-500:]})
        # dnsx failures are non-fatal — we still have subdomains, just not resolved
        logger.warning("dnsx failed (exit %d): %s", exit_code, output[-200:])
        return {}

    await emitter.emit("tool_completed", {"tool": "dnsx"})

    # Parse dnsx JSON output — each line: {"host": "x", "a": ["1.2.3.4"]}
    resolved: dict[str, list[str]] = {}
    try:
        raw_output = await docker.read_file_from_container("dnsx", output_file)
        import json
        for line in raw_output.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                host = entry.get("host", "")
                ips = entry.get("a", [])
                if host and isinstance(ips, list):
                    resolved[host] = [ip for ip in ips if isinstance(ip, str)]
            except (json.JSONDecodeError, ValueError):
                continue
    except ToolExecutionError:
        logger.warning("Could not read dnsx output from %s", output_file)

    await emitter.emit("tool_result", {
        "tool": "dnsx",
        "resolved": len(resolved),
    })
    return resolved


# ── Phase orchestrator ────────────────────────────────────────────────


async def run_phase_recon(
    docker: DockerManager,
    config: dict[str, Any],
    results_dir: str,
    emitter: EventEmitter,
    db_session_factory: async_sessionmaker[AsyncSession],
    scan_id: int,
) -> None:
    """Orchestrate Phase 1: Recon.

    1. Run theHarvester + Amass in parallel (asyncio.gather, return_exceptions=True)
    2. Merge and deduplicate results
    3. Run dnsx for DNS resolution
    4. Save targets to the database
    """
    # Ensure the target_domain is in config for tool runners
    async with db_session_factory() as session:
        from app.models.scan import Scan
        result = await session.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        if scan is not None:
            config = {**config, "target_domain": scan.target_domain}

    # Run harvester and amass in parallel
    results = await asyncio.gather(
        run_theharvester(docker, config, results_dir, emitter),
        run_amass(docker, config, results_dir, emitter),
        return_exceptions=True,
    )

    # Process whatever succeeded
    harvester_result: HarvesterResult
    amass_result: AmassResult

    if isinstance(results[0], Exception):
        logger.warning("theHarvester failed: %s", results[0])
        await emitter.emit("tool_error", {"tool": "theharvester", "error": str(results[0])[:500]})
        harvester_result = HarvesterResult()
    else:
        harvester_result = results[0]

    if isinstance(results[1], Exception):
        logger.warning("Amass failed: %s", results[1])
        await emitter.emit("tool_error", {"tool": "amass", "error": str(results[1])[:500]})
        amass_result = AmassResult()
    else:
        amass_result = results[1]

    # If both tools failed and yielded zero results, raise to fail the phase
    if not harvester_result.subdomains and not amass_result.subdomains and not harvester_result.ips and not amass_result.ips:
        # Only raise if both were exceptions (true failures); empty results are OK
        if isinstance(results[0], Exception) and isinstance(results[1], Exception):
            raise ToolExecutionError(
                tool="recon",
                message="Both theHarvester and Amass failed — no recon data collected",
            )

    # Merge and deduplicate
    all_subdomains = list(set(harvester_result.subdomains + amass_result.subdomains))
    all_ips = list(set(harvester_result.ips + amass_result.ips))
    all_emails = list(set(harvester_result.emails))

    await emitter.emit("recon_merged", {
        "subdomains": len(all_subdomains),
        "ips": len(all_ips),
        "emails": len(all_emails),
    })

    # DNS resolution via dnsx
    dns_resolved = await run_dnsx(docker, all_subdomains, results_dir, emitter)

    # Save targets to database
    async with db_session_factory() as session:
        # Save subdomains
        for subdomain in all_subdomains:
            source = "theharvester+amass"
            if subdomain in [s for s in harvester_result.subdomains] and subdomain not in amass_result.subdomains:
                source = "theharvester"
            elif subdomain in amass_result.subdomains and subdomain not in harvester_result.subdomains:
                source = "amass"

            resolved_ips = dns_resolved.get(subdomain, [])
            target = Target(
                scan_id=scan_id,
                target_type=TargetType.SUBDOMAIN,
                value=subdomain,
                source_tool=source,
                is_live=len(resolved_ips) > 0,
                resolved_ips=resolved_ips if resolved_ips else None,
            )
            session.add(target)

        # Save IPs
        for ip in all_ips:
            source = "theharvester+amass"
            if ip in harvester_result.ips and ip not in amass_result.ips:
                source = "theharvester"
            elif ip in amass_result.ips and ip not in harvester_result.ips:
                source = "amass"

            target = Target(
                scan_id=scan_id,
                target_type=TargetType.IP,
                value=ip,
                source_tool=source,
                is_live=True,
            )
            session.add(target)

        # Save emails
        for email in all_emails:
            target = Target(
                scan_id=scan_id,
                target_type=TargetType.EMAIL,
                value=email,
                source_tool="theharvester",
                is_live=False,
            )
            session.add(target)

        await session.commit()

    logger.info(
        "Phase 1 recon complete: %d subdomains, %d IPs, %d emails, %d DNS resolved",
        len(all_subdomains),
        len(all_ips),
        len(all_emails),
        len(dns_resolved),
    )
