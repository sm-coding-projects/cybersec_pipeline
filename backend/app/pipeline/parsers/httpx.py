"""Parser for httpx (projectdiscovery) JSONL output.

httpx probes HTTP endpoints and outputs one JSON object per line with
fields like ``url``, ``status_code``, ``title``, ``tech``, ``host``,
and ``port``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class HttpxResult:
    """A single HTTP endpoint probed by httpx."""

    url: str
    status_code: int
    title: str
    technologies: list[str] = field(default_factory=list)
    host: str = ""
    port: int = 0


def parse_httpx_output(filepath: str) -> list[HttpxResult]:
    """Parse httpx JSONL output file into a list of ``HttpxResult`` objects.

    Malformed lines are skipped with a warning.
    """
    results: list[HttpxResult] = []

    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            for line_no, raw_line in enumerate(fh, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("httpx: skipping malformed line %d in %s", line_no, filepath)
                    continue

                if not isinstance(entry, dict):
                    continue

                url = entry.get("url", "")
                if not isinstance(url, str) or not url.strip():
                    continue

                # Status code
                status_code = entry.get("status_code", entry.get("status-code", 0))
                if not isinstance(status_code, int):
                    try:
                        status_code = int(status_code)
                    except (ValueError, TypeError):
                        status_code = 0

                # Title
                title = entry.get("title", "")
                if not isinstance(title, str):
                    title = str(title)

                # Technologies — httpx uses "tech" key
                technologies = entry.get("tech", entry.get("technologies", []))
                if not isinstance(technologies, list):
                    technologies = []
                technologies = [str(t) for t in technologies if t]

                # Host and port
                host = entry.get("host", entry.get("input", ""))
                if not isinstance(host, str):
                    host = str(host)

                port_raw = entry.get("port", 0)
                try:
                    port = int(port_raw)
                except (ValueError, TypeError):
                    port = 0

                results.append(
                    HttpxResult(
                        url=url.strip(),
                        status_code=status_code,
                        title=title.strip(),
                        technologies=technologies,
                        host=host.strip(),
                        port=port,
                    )
                )

    except FileNotFoundError:
        logger.warning("httpx output file not found: %s", filepath)
        return []

    logger.info("Parsed httpx output: %d endpoints", len(results))
    return results
