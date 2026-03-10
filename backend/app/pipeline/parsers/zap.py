"""Parser for ZAP (Zed Attack Proxy) JSON report output.

ZAP outputs a JSON report with the structure:
``{"site": [{"alerts": [...]}]}`` or sometimes ``{"site": [{"@name": "...", "alerts": [...]}]}``.
Each alert contains fields like ``alert``, ``riskdesc``, ``confidence``,
``uri`` (or within ``instances``), ``desc``, ``solution``, ``reference``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ZapAlert:
    """A single alert from a ZAP scan."""

    alert: str
    risk: str
    confidence: str
    url: str
    description: str
    solution: str
    reference: str


def _extract_risk(entry: dict) -> str:
    """Extract the risk level from a ZAP alert entry.

    ZAP uses ``riskdesc`` which looks like ``"High (Medium)"`` or
    just a ``risk`` field with a numeric code. We prefer a clean
    string representation.
    """
    riskdesc = entry.get("riskdesc", "")
    if isinstance(riskdesc, str) and riskdesc.strip():
        # Take just the risk part before the confidence in parentheses
        return riskdesc.split("(")[0].strip()

    risk_code = entry.get("riskcode", entry.get("risk", ""))
    risk_map: dict[str, str] = {"3": "High", "2": "Medium", "1": "Low", "0": "Informational"}
    return risk_map.get(str(risk_code), str(risk_code))


def _extract_confidence(entry: dict) -> str:
    """Extract the confidence level from a ZAP alert entry."""
    riskdesc = entry.get("riskdesc", "")
    if isinstance(riskdesc, str) and "(" in riskdesc:
        # "High (Medium)" → "Medium"
        try:
            return riskdesc.split("(")[1].rstrip(")")
        except IndexError:
            pass

    confidence_code = entry.get("confidence", "")
    conf_map: dict[str, str] = {"3": "High", "2": "Medium", "1": "Low", "0": "False Positive"}
    return conf_map.get(str(confidence_code), str(confidence_code))


def _extract_url(entry: dict) -> str:
    """Extract the primary URL from a ZAP alert.

    ZAP may store URLs in different locations: top-level ``url``,
    ``uri``, or within an ``instances`` array.
    """
    # Direct URL fields
    for key in ("url", "uri"):
        val = entry.get(key, "")
        if isinstance(val, str) and val.strip():
            return val.strip()

    # Check instances array (ZAP often puts URLs here)
    instances = entry.get("instances", [])
    if isinstance(instances, list) and instances:
        first = instances[0]
        if isinstance(first, dict):
            uri = first.get("uri", first.get("url", ""))
            if isinstance(uri, str) and uri.strip():
                return uri.strip()

    return ""


def parse_zap_output(filepath: str) -> list[ZapAlert]:
    """Parse ZAP JSON report into a list of ``ZapAlert`` objects.

    Handles various ZAP output formats and malformed data gracefully.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        logger.warning("ZAP output file not found: %s", filepath)
        return []
    except json.JSONDecodeError as exc:
        logger.warning("ZAP output is not valid JSON (%s): %s", filepath, exc)
        return []

    if not isinstance(data, dict):
        logger.warning("ZAP output is not a JSON object: %s", filepath)
        return []

    alerts_list: list[ZapAlert] = []

    # ZAP JSON report structure: {"site": [{"alerts": [...]}]}
    sites = data.get("site", [])
    if isinstance(sites, dict):
        # Sometimes a single site is a dict, not a list
        sites = [sites]
    if not isinstance(sites, list):
        logger.warning("ZAP output 'site' field is not a list or dict: %s", filepath)
        return []

    for site in sites:
        if not isinstance(site, dict):
            continue

        site_alerts = site.get("alerts", [])
        if not isinstance(site_alerts, list):
            continue

        for entry in site_alerts:
            if not isinstance(entry, dict):
                continue

            alert_name = entry.get("alert", entry.get("name", ""))
            if not isinstance(alert_name, str) or not alert_name.strip():
                continue

            description = entry.get("desc", entry.get("description", ""))
            if not isinstance(description, str):
                description = str(description)

            solution = entry.get("solution", "")
            if not isinstance(solution, str):
                solution = str(solution)

            reference = entry.get("reference", "")
            if not isinstance(reference, str):
                reference = str(reference)

            alerts_list.append(
                ZapAlert(
                    alert=alert_name.strip(),
                    risk=_extract_risk(entry),
                    confidence=_extract_confidence(entry),
                    url=_extract_url(entry),
                    description=description.strip(),
                    solution=solution.strip(),
                    reference=reference.strip(),
                )
            )

    logger.info("Parsed ZAP output: %d alerts", len(alerts_list))
    return alerts_list
