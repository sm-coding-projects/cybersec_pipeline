"""Tests for the httpx output parser."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from app.pipeline.parsers.httpx import HttpxResult, parse_httpx_output


def _write_jsonl(lines: list[dict]) -> str:
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return path


class TestParseHttpxOutput:
    def test_valid_output(self) -> None:
        data = [
            {
                "url": "https://example.com",
                "status_code": 200,
                "title": "Example Domain",
                "tech": ["Nginx", "PHP"],
                "host": "example.com",
                "port": 443,
            },
            {
                "url": "http://sub.example.com",
                "status_code": 301,
                "title": "Redirect",
                "host": "sub.example.com",
                "port": 80,
            },
        ]
        path = _write_jsonl(data)
        try:
            results = parse_httpx_output(path)
            assert len(results) == 2
            assert isinstance(results[0], HttpxResult)
            assert results[0].url == "https://example.com"
            assert results[0].status_code == 200
            assert results[0].title == "Example Domain"
            assert results[0].technologies == ["Nginx", "PHP"]
            assert results[0].host == "example.com"
            assert results[0].port == 443
        finally:
            os.unlink(path)

    def test_empty_technologies(self) -> None:
        data = [{"url": "https://example.com", "status_code": 200, "title": "Test"}]
        path = _write_jsonl(data)
        try:
            results = parse_httpx_output(path)
            assert len(results) == 1
            assert results[0].technologies == []
        finally:
            os.unlink(path)

    def test_malformed_line_skipped(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"url": "https://good.com", "status_code": 200, "title": "Good"}) + "\n")
            f.write("not json\n")
            f.write(json.dumps({"url": "https://also-good.com", "status_code": 200, "title": "OK"}) + "\n")
        try:
            results = parse_httpx_output(path)
            assert len(results) == 2
        finally:
            os.unlink(path)

    def test_file_not_found(self) -> None:
        results = parse_httpx_output("/nonexistent/file.jsonl")
        assert results == []

    def test_missing_url_skipped(self) -> None:
        data = [{"status_code": 200, "title": "No URL"}]
        path = _write_jsonl(data)
        try:
            results = parse_httpx_output(path)
            assert results == []
        finally:
            os.unlink(path)

    def test_status_code_as_string(self) -> None:
        data = [{"url": "https://example.com", "status_code": "200", "title": "Test"}]
        path = _write_jsonl(data)
        try:
            results = parse_httpx_output(path)
            assert len(results) == 1
            assert results[0].status_code == 200
        finally:
            os.unlink(path)

    def test_alternative_field_names(self) -> None:
        """httpx may use 'status-code' or 'input' in some versions."""
        data = [{"url": "https://example.com", "status-code": 200, "title": "Test", "input": "example.com"}]
        path = _write_jsonl(data)
        try:
            results = parse_httpx_output(path)
            assert len(results) == 1
            assert results[0].status_code == 200
            assert results[0].host == "example.com"
        finally:
            os.unlink(path)
