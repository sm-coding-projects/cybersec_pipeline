"""Parser for Nuclei JSONL output.

Nuclei outputs one JSON object per line.  Each entry contains fields
like ``template-id``, ``info`` (with ``name``, ``severity``,
``description``, ``reference``), ``host``, ``matched-at``, and
optionally ``extracted-results``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from app.models.base import Severity

logger = logging.getLogger(__name__)


@dataclass
class NucleiFinding:
    """A single vulnerability finding from Nuclei."""

    template_id: str
    name: str
    severity: Severity
    host: str
    url: str | None
    matched_at: str
    description: str
    reference: list[str] = field(default_factory=list)
    extracted_results: list[str] | None = None


def _parse_severity(raw: str) -> Severity:
    """Map a raw severity string to the ``Severity`` enum.

    Falls back to ``Severity.INFO`` for unrecognised values.
    """
    mapping: dict[str, Severity] = {
        "critical": Severity.CRITICAL,
        "high": Severity.HIGH,
        "medium": Severity.MEDIUM,
        "low": Severity.LOW,
        "info": Severity.INFO,
        "informational": Severity.INFO,
    }
    return mapping.get(raw.strip().lower(), Severity.INFO)


def parse_nuclei_output(filepath: str) -> list[NucleiFinding]:
    """Parse Nuclei JSONL output file into a list of ``NucleiFinding`` objects.

    Malformed lines are skipped with a warning.
    """
    findings: list[NucleiFinding] = []

    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            for line_no, raw_line in enumerate(fh, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Nuclei: skipping malformed line %d in %s", line_no, filepath)
                    continue

                if not isinstance(entry, dict):
                    continue

                info: dict = entry.get("info", {})
                if not isinstance(info, dict):
                    info = {}

                # Reference may be a list or None
                reference = info.get("reference", [])
                if reference is None:
                    reference = []
                if isinstance(reference, str):
                    reference = [reference]
                if not isinstance(reference, list):
                    reference = []

                # Extracted results may be a list or None
                extracted = entry.get("extracted-results")
                if extracted is not None and not isinstance(extracted, list):
                    extracted = [str(extracted)]

                findings.append(
                    NucleiFinding(
                        template_id=entry.get("template-id", entry.get("templateID", "")),
                        name=info.get("name", "Unknown"),
                        severity=_parse_severity(info.get("severity", "info")),
                        host=entry.get("host", ""),
                        url=entry.get("matched-at"),
                        matched_at=entry.get("matched-at", ""),
                        description=info.get("description", ""),
                        reference=[str(r) for r in reference if r],
                        extracted_results=extracted,
                    )
                )

    except FileNotFoundError:
        logger.warning("Nuclei output file not found: %s", filepath)
        return []

    logger.info("Parsed Nuclei output: %d findings", len(findings))
    return findings
