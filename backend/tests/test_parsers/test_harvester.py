"""Tests for the theHarvester output parser."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from app.pipeline.parsers.harvester import HarvesterResult, parse_harvester_output


@pytest.fixture
def sample_harvester_json() -> dict:
    return {
        "hosts": [
            "sub1.example.com:1.2.3.4",
            "sub2.example.com",
            "sub1.example.com:5.6.7.8",
        ],
        "ips": ["1.2.3.4", "5.6.7.8", "9.10.11.12"],
        "emails": ["admin@example.com", "info@example.com"],
    }


def _write_json(data, suffix=".json") -> str:
    """Write data to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    return path


class TestParseHarvesterOutput:
    def test_valid_output(self, sample_harvester_json: dict) -> None:
        path = _write_json(sample_harvester_json)
        try:
            result = parse_harvester_output(path)
            assert isinstance(result, HarvesterResult)
            assert len(result.ips) == 3
            assert len(result.emails) == 2
            # Subdomains should be deduplicated (sub1.example.com appears twice)
            assert "sub1.example.com" in result.subdomains
            assert "sub2.example.com" in result.subdomains
        finally:
            os.unlink(path)

    def test_empty_fields(self) -> None:
        path = _write_json({"hosts": [], "ips": [], "emails": []})
        try:
            result = parse_harvester_output(path)
            assert result.subdomains == []
            assert result.ips == []
            assert result.emails == []
        finally:
            os.unlink(path)

    def test_missing_keys(self) -> None:
        path = _write_json({"hosts": ["sub.example.com"]})
        try:
            result = parse_harvester_output(path)
            assert len(result.subdomains) == 1
            assert result.ips == []
            assert result.emails == []
        finally:
            os.unlink(path)

    def test_file_not_found(self) -> None:
        result = parse_harvester_output("/nonexistent/file.json")
        assert isinstance(result, HarvesterResult)
        assert result.subdomains == []
        assert result.ips == []

    def test_invalid_json(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            f.write("not valid json {{{")
        try:
            result = parse_harvester_output(path)
            assert isinstance(result, HarvesterResult)
            assert result.subdomains == []
        finally:
            os.unlink(path)

    def test_non_dict_json(self) -> None:
        path = _write_json([1, 2, 3])
        try:
            result = parse_harvester_output(path)
            assert isinstance(result, HarvesterResult)
            assert result.subdomains == []
        finally:
            os.unlink(path)

    def test_host_colon_split(self) -> None:
        """Hosts in format 'subdomain:ip' should extract just the subdomain."""
        path = _write_json({"hosts": ["web.example.com:10.0.0.1"]})
        try:
            result = parse_harvester_output(path)
            assert "web.example.com" in result.subdomains
        finally:
            os.unlink(path)

    def test_deduplication(self) -> None:
        path = _write_json(
            {
                "hosts": ["a.example.com", "a.example.com", "b.example.com"],
                "ips": ["1.1.1.1", "1.1.1.1"],
                "emails": ["x@example.com", "x@example.com"],
            }
        )
        try:
            result = parse_harvester_output(path)
            assert len(result.subdomains) == 2
            assert len(result.ips) == 1
            assert len(result.emails) == 1
        finally:
            os.unlink(path)
