"""Tests for the Amass v4 plain-text output parser."""

from __future__ import annotations

import os
import tempfile

import pytest

from app.pipeline.parsers.amass import AmassResult, parse_amass_output


def _write_txt(lines: list[str]) -> str:
    """Write lines to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


class TestParseAmassOutput:
    def test_valid_output(self) -> None:
        path = _write_txt(["sub1.example.com", "sub2.example.com", "sub3.example.com"])
        try:
            result = parse_amass_output(path)
            assert isinstance(result, AmassResult)
            assert len(result.subdomains) == 3
            assert "sub1.example.com" in result.subdomains
        finally:
            os.unlink(path)

    def test_no_ips_in_result(self) -> None:
        """Amass v4 text output contains no IPs; ips field is always empty."""
        path = _write_txt(["sub.example.com"])
        try:
            result = parse_amass_output(path)
            assert result.ips == []
        finally:
            os.unlink(path)

    def test_empty_file(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            result = parse_amass_output(path)
            assert result.subdomains == []
            assert result.ips == []
        finally:
            os.unlink(path)

    def test_file_not_found(self) -> None:
        result = parse_amass_output("/nonexistent/file.txt")
        assert isinstance(result, AmassResult)
        assert result.subdomains == []

    def test_blank_lines_skipped(self) -> None:
        path = _write_txt(["sub1.example.com", "", "sub2.example.com", ""])
        try:
            result = parse_amass_output(path)
            assert len(result.subdomains) == 2
        finally:
            os.unlink(path)

    def test_comment_lines_skipped(self) -> None:
        path = _write_txt(["# this is a comment", "sub.example.com"])
        try:
            result = parse_amass_output(path)
            assert len(result.subdomains) == 1
            assert "sub.example.com" in result.subdomains
        finally:
            os.unlink(path)

    def test_deduplication(self) -> None:
        path = _write_txt(["sub.example.com", "SUB.EXAMPLE.COM", "sub.example.com"])
        try:
            result = parse_amass_output(path)
            assert len(result.subdomains) == 1
            assert result.subdomains[0] == "sub.example.com"
        finally:
            os.unlink(path)

    def test_lowercased(self) -> None:
        path = _write_txt(["SUB.EXAMPLE.COM"])
        try:
            result = parse_amass_output(path)
            assert result.subdomains == ["sub.example.com"]
        finally:
            os.unlink(path)
