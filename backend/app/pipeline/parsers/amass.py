"""Parser for Amass v4 graph-format output.

Amass v4 writes graph-format output via the ``-o`` flag::

    buildforward.com.au (FQDN) --> a_record --> 192.250.232.174 (IPAddress)
    www.buildforward.com.au (FQDN) --> cname_record --> buildforward.com.au (FQDN)

This parser extracts FQDNs and IP addresses from these lines.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Matches entries like: subdomain.example.com (FQDN)
_FQDN_RE = re.compile(r"([\w.\-]+)\s+\(FQDN\)")
# Matches entries like: 192.168.1.1 (IPAddress)
_IP_RE = re.compile(r"([\d.]+)\s+\(IPAddress\)")


@dataclass
class AmassResult:
    """Structured output from Amass."""

    subdomains: list[str] = field(default_factory=list)
    ips: list[str] = field(default_factory=list)


def parse_amass_output(filepath: str) -> AmassResult:
    """Parse Amass v4 output file into an ``AmassResult``.

    Handles both graph-format (v4) and plain-text (one subdomain per line).
    Graph-format lines contain `` (FQDN) `` and `` (IPAddress) `` markers;
    plain-text lines are bare domain names.
    """
    subdomains: set[str] = set()
    ips: set[str] = set()
    is_graph_format = False

    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                # Detect graph-format lines (contain type markers like "(FQDN)")
                if "(FQDN)" in line or "(IPAddress)" in line:
                    is_graph_format = True
                    for match in _FQDN_RE.finditer(line):
                        fqdn = match.group(1).lower()
                        # Skip non-subdomain entries (NS servers, external FQDNs)
                        # These will be filtered downstream by domain matching
                        subdomains.add(fqdn)
                    for match in _IP_RE.finditer(line):
                        ips.add(match.group(1))
                elif not is_graph_format:
                    # Plain-text fallback: each line is a subdomain
                    subdomains.add(line.lower())
    except FileNotFoundError:
        logger.warning("Amass output file not found: %s", filepath)
        return AmassResult()

    result = AmassResult(subdomains=sorted(subdomains), ips=sorted(ips))
    logger.info("Parsed Amass output: %d subdomains, %d IPs", len(result.subdomains), len(result.ips))
    return result
