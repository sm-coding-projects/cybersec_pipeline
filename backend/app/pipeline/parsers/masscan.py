"""Parser for Masscan JSON output.

IMPORTANT: Masscan's JSON output has trailing commas which make it
invalid JSON.  This parser cleans up the output with a regex before
parsing.  Masscan outputs an array of objects, each with ``ip`` and
``ports`` fields.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MasscanResult:
    """A single host discovered by Masscan with its open ports."""

    ip: str
    ports: list[int] = field(default_factory=list)


def _clean_masscan_json(raw: str) -> str:
    """Remove trailing commas that Masscan leaves in its JSON output.

    Masscan produces output like:
        [
          { ... },
          { ... },
        ]
    The trailing comma before ``]`` is invalid JSON.  We also handle
    trailing commas before ``}`` just in case.
    """
    # Remove trailing commas before ] or }
    cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
    return cleaned


def parse_masscan_output(filepath: str) -> list[MasscanResult]:
    """Parse Masscan JSON output file into a list of ``MasscanResult`` objects.

    Handles trailing commas, missing keys, and malformed files gracefully.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except FileNotFoundError:
        logger.warning("Masscan output file not found: %s", filepath)
        return []

    raw = raw.strip()
    if not raw:
        logger.warning("Masscan output file is empty: %s", filepath)
        return []

    # Clean up trailing commas before parsing
    cleaned = _clean_masscan_json(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("Masscan output is not valid JSON even after cleanup (%s): %s", filepath, exc)
        return []

    if not isinstance(data, list):
        logger.warning("Masscan output is not a JSON array: %s", filepath)
        return []

    # Aggregate ports per IP (Masscan emits one entry per port)
    ip_ports: dict[str, set[int]] = {}

    for entry in data:
        if not isinstance(entry, dict):
            continue

        ip = entry.get("ip", "")
        if not isinstance(ip, str) or not ip.strip():
            continue

        ports = entry.get("ports", [])
        if not isinstance(ports, list):
            continue

        for port_info in ports:
            if isinstance(port_info, dict):
                port_num = port_info.get("port")
                if isinstance(port_num, int):
                    ip_ports.setdefault(ip, set()).add(port_num)
            elif isinstance(port_info, int):
                ip_ports.setdefault(ip, set()).add(port_info)

    results: list[MasscanResult] = [
        MasscanResult(ip=ip, ports=sorted(ports)) for ip, ports in sorted(ip_ports.items())
    ]

    logger.info(
        "Parsed Masscan output: %d hosts, %d total open ports",
        len(results),
        sum(len(r.ports) for r in results),
    )
    return results
