"""Tests for the ZAP JSON report parser."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from app.pipeline.parsers.zap import ZapAlert, parse_zap_output


def _write_json(data) -> str:
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    return path


SAMPLE_ZAP_REPORT = {
    "site": [
        {
            "@name": "https://example.com",
            "alerts": [
                {
                    "alert": "Cross-Site Scripting (Reflected)",
                    "riskdesc": "High (Medium)",
                    "desc": "Cross-site scripting vulnerability found",
                    "solution": "Validate and encode user input",
                    "reference": "https://owasp.org/xss",
                    "instances": [{"uri": "https://example.com/search?q=test"}],
                },
                {
                    "alert": "Missing Security Headers",
                    "riskdesc": "Low (High)",
                    "desc": "Security headers are missing",
                    "solution": "Add X-Content-Type-Options, etc.",
                    "reference": "",
                    "uri": "https://example.com",
                },
            ],
        }
    ]
}


class TestParseZapOutput:
    def test_valid_output(self) -> None:
        path = _write_json(SAMPLE_ZAP_REPORT)
        try:
            alerts = parse_zap_output(path)
            assert len(alerts) == 2
            assert isinstance(alerts[0], ZapAlert)

            xss = alerts[0]
            assert xss.alert == "Cross-Site Scripting (Reflected)"
            assert xss.risk == "High"
            assert xss.confidence == "Medium"
            assert xss.url == "https://example.com/search?q=test"
            assert "cross-site scripting" in xss.description.lower()

            headers = alerts[1]
            assert headers.risk == "Low"
            assert headers.confidence == "High"
            assert headers.url == "https://example.com"
        finally:
            os.unlink(path)

    def test_single_site_as_dict(self) -> None:
        """ZAP sometimes outputs site as a single dict instead of a list."""
        report = {
            "site": {
                "alerts": [
                    {
                        "alert": "Test Alert",
                        "riskdesc": "Medium (Medium)",
                        "desc": "Test",
                        "solution": "Fix it",
                        "reference": "",
                        "uri": "https://example.com",
                    }
                ]
            }
        }
        path = _write_json(report)
        try:
            alerts = parse_zap_output(path)
            assert len(alerts) == 1
            assert alerts[0].risk == "Medium"
        finally:
            os.unlink(path)

    def test_empty_alerts(self) -> None:
        report = {"site": [{"alerts": []}]}
        path = _write_json(report)
        try:
            alerts = parse_zap_output(path)
            assert alerts == []
        finally:
            os.unlink(path)

    def test_no_site_key(self) -> None:
        path = _write_json({"other": "data"})
        try:
            alerts = parse_zap_output(path)
            assert alerts == []
        finally:
            os.unlink(path)

    def test_file_not_found(self) -> None:
        alerts = parse_zap_output("/nonexistent/file.json")
        assert alerts == []

    def test_invalid_json(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            f.write("not json")
        try:
            alerts = parse_zap_output(path)
            assert alerts == []
        finally:
            os.unlink(path)

    def test_risk_code_fallback(self) -> None:
        """When riskdesc is missing, fall back to riskcode."""
        report = {
            "site": [
                {
                    "alerts": [
                        {
                            "alert": "Test",
                            "riskcode": "3",
                            "confidence": "2",
                            "desc": "Test",
                            "solution": "",
                            "reference": "",
                            "uri": "https://example.com",
                        }
                    ]
                }
            ]
        }
        path = _write_json(report)
        try:
            alerts = parse_zap_output(path)
            assert len(alerts) == 1
            assert alerts[0].risk == "High"
            assert alerts[0].confidence == "Medium"
        finally:
            os.unlink(path)

    def test_url_from_instances(self) -> None:
        """URL should be extracted from instances array when no direct uri."""
        report = {
            "site": [
                {
                    "alerts": [
                        {
                            "alert": "Test",
                            "riskdesc": "High (High)",
                            "desc": "Test",
                            "solution": "",
                            "reference": "",
                            "instances": [
                                {"uri": "https://example.com/vulnerable-page"}
                            ],
                        }
                    ]
                }
            ]
        }
        path = _write_json(report)
        try:
            alerts = parse_zap_output(path)
            assert alerts[0].url == "https://example.com/vulnerable-page"
        finally:
            os.unlink(path)
