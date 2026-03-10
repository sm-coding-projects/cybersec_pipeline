"""Tests for the Amass output parser."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from app.pipeline.parsers.amass import AmassResult, parse_amass_output


def _write_jsonl(lines: list[dict]) -> str:
    """Write a list of dicts as JSONL to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return path


class TestParseAmassOutput:
    def test_valid_output(self) -> None:
        data = [
            {"name": "sub1.example.com", "addresses": [{"ip": "1.2.3.4"}]},
            {"name": "sub2.example.com", "addresses": [{"ip": "5.6.7.8"}, {"ip": "9.10.11.12"}]},
        ]
        path = _write_jsonl(data)
        try:
            result = parse_amass_output(path)
            assert isinstance(result, AmassResult)
            assert len(result.subdomains) == 2
            assert "sub1.example.com" in result.subdomains
            assert len(result.ips) == 3
        finally:
            os.unlink(path)

    def test_no_addresses(self) -> None:
        data = [{"name": "sub.example.com"}]
        path = _write_jsonl(data)
        try:
            result = parse_amass_output(path)
            assert len(result.subdomains) == 1
            assert result.ips == []
        finally:
            os.unlink(path)

    def test_empty_file(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        try:
            result = parse_amass_output(path)
            assert result.subdomains == []
            assert result.ips == []
        finally:
            os.unlink(path)

    def test_file_not_found(self) -> None:
        result = parse_amass_output("/nonexistent/file.jsonl")
        assert isinstance(result, AmassResult)
        assert result.subdomains == []

    def test_malformed_line_skipped(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(fd, "w") as f:
            f.write('{"name": "good.example.com"}\n')
            f.write("not valid json\n")
            f.write('{"name": "also-good.example.com"}\n')
        try:
            result = parse_amass_output(path)
            assert len(result.subdomains) == 2
        finally:
            os.unlink(path)

    def test_deduplication(self) -> None:
        data = [
            {"name": "sub.example.com", "addresses": [{"ip": "1.2.3.4"}]},
            {"name": "SUB.EXAMPLE.COM", "addresses": [{"ip": "1.2.3.4"}]},
        ]
        path = _write_jsonl(data)
        try:
            result = parse_amass_output(path)
            # Both should be lowercased and deduplicated
            assert len(result.subdomains) == 1
            assert len(result.ips) == 1
        finally:
            os.unlink(path)

    def test_addresses_as_strings(self) -> None:
        """Some Amass versions emit addresses as plain strings."""
        data = [{"name": "sub.example.com", "addresses": ["1.2.3.4", "5.6.7.8"]}]
        path = _write_jsonl(data)
        try:
            result = parse_amass_output(path)
            assert len(result.ips) == 2
        finally:
            os.unlink(path)
