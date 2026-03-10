"""Parser for Amass JSONL output.

Amass outputs one JSON object per line.  Each line contains a ``name`` field
(subdomain) and an ``addresses`` array with ``ip`` entries.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AmassResult:
    """Structured output from Amass."""

    subdomains: list[str] = field(default_factory=list)
    ips: list[str] = field(default_factory=list)


def parse_amass_output(filepath: str) -> AmassResult:
    """Parse Amass JSONL output file into an ``AmassResult``.

    Each line is expected to be a JSON object with at least a ``name`` field.
    Malformed lines are skipped with a warning.
    """
    subdomains: set[str] = set()
    ips: set[str] = set()

    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            for line_no, raw_line in enumerate(fh, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Amass: skipping malformed line %d in %s", line_no, filepath)
                    continue

                if not isinstance(entry, dict):
                    continue

                # Subdomain name
                name = entry.get("name", "")
                if isinstance(name, str) and name.strip():
                    subdomains.add(name.strip().lower())

                # IP addresses from the 'addresses' array
                addresses = entry.get("addresses", [])
                if isinstance(addresses, list):
                    for addr in addresses:
                        if isinstance(addr, dict):
                            ip = addr.get("ip", "")
                            if isinstance(ip, str) and ip.strip():
                                ips.add(ip.strip())
                        elif isinstance(addr, str) and addr.strip():
                            ips.add(addr.strip())

    except FileNotFoundError:
        logger.warning("Amass output file not found: %s", filepath)
        return AmassResult()

    result = AmassResult(subdomains=sorted(subdomains), ips=sorted(ips))
    logger.info(
        "Parsed Amass output: %d subdomains, %d IPs",
        len(result.subdomains),
        len(result.ips),
    )
    return result
