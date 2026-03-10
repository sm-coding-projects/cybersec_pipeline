"""Parser for theHarvester JSON output.

theHarvester writes a JSON file with keys like ``hosts``, ``ips``, ``emails``.
This parser reads that file and returns a typed ``HarvesterResult``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class HarvesterResult:
    """Structured output from theHarvester."""

    subdomains: list[str] = field(default_factory=list)
    ips: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)


def parse_harvester_output(filepath: str) -> HarvesterResult:
    """Parse theHarvester JSON output file into a ``HarvesterResult``.

    Handles missing keys, malformed JSON, and empty files gracefully.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        logger.warning("theHarvester output file not found: %s", filepath)
        return HarvesterResult()
    except json.JSONDecodeError as exc:
        logger.warning("theHarvester output is not valid JSON (%s): %s", filepath, exc)
        return HarvesterResult()

    if not isinstance(data, dict):
        logger.warning("theHarvester output is not a JSON object: %s", filepath)
        return HarvesterResult()

    # theHarvester uses 'hosts' for subdomains (list of strings or list of "host:ip" strings).
    raw_hosts: list = data.get("hosts", [])
    subdomains: list[str] = []
    for entry in raw_hosts:
        if not isinstance(entry, str):
            continue
        # Some versions output "sub.example.com:1.2.3.4" — take just the hostname.
        hostname = entry.split(":")[0].strip().lower()
        if hostname:
            subdomains.append(hostname)

    # IPs
    raw_ips: list = data.get("ips", [])
    ips: list[str] = [ip for ip in raw_ips if isinstance(ip, str) and ip.strip()]

    # Emails
    raw_emails: list = data.get("emails", [])
    emails: list[str] = [e for e in raw_emails if isinstance(e, str) and e.strip()]

    result = HarvesterResult(
        subdomains=list(set(subdomains)),
        ips=list(set(ips)),
        emails=list(set(emails)),
    )
    logger.info(
        "Parsed theHarvester output: %d subdomains, %d IPs, %d emails",
        len(result.subdomains),
        len(result.ips),
        len(result.emails),
    )
    return result
