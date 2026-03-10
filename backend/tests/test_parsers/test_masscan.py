"""Tests for the Masscan JSON output parser."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from app.pipeline.parsers.masscan import MasscanResult, parse_masscan_output


def _write_file(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


class TestParseMasscanOutput:
    def test_valid_output(self) -> None:
        data = [
            {"ip": "1.2.3.4", "ports": [{"port": 80, "proto": "tcp", "status": "open"}]},
            {"ip": "5.6.7.8", "ports": [{"port": 443, "proto": "tcp", "status": "open"}]},
        ]
        path = _write_file(json.dumps(data))
        try:
            results = parse_masscan_output(path)
            assert len(results) == 2
            assert isinstance(results[0], MasscanResult)
            ips = {r.ip for r in results}
            assert "1.2.3.4" in ips
            assert "5.6.7.8" in ips
        finally:
            os.unlink(path)

    def test_trailing_commas(self) -> None:
        """Masscan output with trailing commas should be handled."""
        content = """\
[
  {"ip": "1.2.3.4", "ports": [{"port": 80}]},
  {"ip": "5.6.7.8", "ports": [{"port": 443}]},
]
"""
        path = _write_file(content)
        try:
            results = parse_masscan_output(path)
            assert len(results) == 2
        finally:
            os.unlink(path)

    def test_port_aggregation(self) -> None:
        """Multiple entries for the same IP should aggregate ports."""
        data = [
            {"ip": "1.2.3.4", "ports": [{"port": 80}]},
            {"ip": "1.2.3.4", "ports": [{"port": 443}]},
            {"ip": "1.2.3.4", "ports": [{"port": 8080}]},
        ]
        path = _write_file(json.dumps(data))
        try:
            results = parse_masscan_output(path)
            assert len(results) == 1
            assert sorted(results[0].ports) == [80, 443, 8080]
        finally:
            os.unlink(path)

    def test_empty_file(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            results = parse_masscan_output(path)
            assert results == []
        finally:
            os.unlink(path)

    def test_file_not_found(self) -> None:
        results = parse_masscan_output("/nonexistent/file.json")
        assert results == []

    def test_invalid_json(self) -> None:
        path = _write_file("totally broken {{{")
        try:
            results = parse_masscan_output(path)
            assert results == []
        finally:
            os.unlink(path)

    def test_non_array_json(self) -> None:
        path = _write_file('{"ip": "1.2.3.4"}')
        try:
            results = parse_masscan_output(path)
            assert results == []
        finally:
            os.unlink(path)

    def test_empty_array(self) -> None:
        path = _write_file("[]")
        try:
            results = parse_masscan_output(path)
            assert results == []
        finally:
            os.unlink(path)
