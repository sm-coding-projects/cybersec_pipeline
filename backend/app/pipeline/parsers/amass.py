"""Parser for Amass v4 plain-text output.

Amass v4 removed the ``-json`` flag.  The ``-o <prefix>`` flag writes one
subdomain per line to ``<prefix>.txt``.  IP addresses are no longer included
in the enum output; resolution is handled downstream by dnsx.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AmassResult:
    """Structured output from Amass."""

    subdomains: list[str] = field(default_factory=list)
    ips: list[str] = field(default_factory=list)


def parse_amass_output(filepath: str) -> AmassResult:
    """Parse Amass v4 plain-text output file into an ``AmassResult``.

    Each non-empty line is treated as a subdomain name.  Lines starting with
    ``#`` are skipped.  Results are lowercased and deduplicated.
    """
    subdomains: set[str] = set()

    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                subdomains.add(line.lower())
    except FileNotFoundError:
        logger.warning("Amass output file not found: %s", filepath)
        return AmassResult()

    result = AmassResult(subdomains=sorted(subdomains))
    logger.info("Parsed Amass output: %d subdomains", len(result.subdomains))
    return result
