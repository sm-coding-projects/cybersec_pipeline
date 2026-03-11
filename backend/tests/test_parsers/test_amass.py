"""Tests for the Amass output parser (v4 graph-format + plain-text fallback)."""

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


class TestParseAmassPlainText:
    """Tests for plain-text fallback (one subdomain per line)."""

    def test_valid_output(self) -> None:
        path = _write_txt(["sub1.example.com", "sub2.example.com", "sub3.example.com"])
        try:
            result = parse_amass_output(path)
            assert isinstance(result, AmassResult)
            assert len(result.subdomains) == 3
            assert "sub1.example.com" in result.subdomains
        finally:
            os.unlink(path)

    def test_no_ips_in_plain_text(self) -> None:
        """Plain-text output contains no IPs; ips field is always empty."""
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


class TestParseAmassGraphFormat:
    """Tests for Amass v4 graph-format output."""

    def test_graph_format_extracts_fqdns_and_ips(self) -> None:
        """Graph-format lines should extract FQDNs and IPAddresses."""
        path = _write_txt([
            "sub1.example.com (FQDN) --> a_record --> 1.2.3.4 (IPAddress)",
            "sub2.example.com (FQDN) --> a_record --> 5.6.7.8 (IPAddress)",
        ])
        try:
            result = parse_amass_output(path)
            assert len(result.subdomains) == 2
            assert "sub1.example.com" in result.subdomains
            assert "sub2.example.com" in result.subdomains
            assert len(result.ips) == 2
            assert "1.2.3.4" in result.ips
            assert "5.6.7.8" in result.ips
        finally:
            os.unlink(path)

    def test_graph_format_cname_records(self) -> None:
        """CNAME records should extract both FQDNs but no IPs."""
        path = _write_txt([
            "www.example.com (FQDN) --> cname_record --> example.com (FQDN)",
        ])
        try:
            result = parse_amass_output(path)
            assert len(result.subdomains) == 2
            assert "www.example.com" in result.subdomains
            assert "example.com" in result.subdomains
            assert result.ips == []
        finally:
            os.unlink(path)

    def test_graph_format_deduplication(self) -> None:
        """Duplicate FQDNs and IPs across lines should be deduplicated."""
        path = _write_txt([
            "sub.example.com (FQDN) --> a_record --> 1.2.3.4 (IPAddress)",
            "sub.example.com (FQDN) --> a_record --> 1.2.3.4 (IPAddress)",
            "sub.example.com (FQDN) --> cname_record --> other.example.com (FQDN)",
        ])
        try:
            result = parse_amass_output(path)
            assert len(result.subdomains) == 2  # sub + other
            assert len(result.ips) == 1
        finally:
            os.unlink(path)

    def test_graph_format_with_blank_and_comment_lines(self) -> None:
        """Blank lines and comments should be skipped in graph-format output."""
        path = _write_txt([
            "# Amass v4 output",
            "",
            "sub.example.com (FQDN) --> a_record --> 10.0.0.1 (IPAddress)",
            "",
        ])
        try:
            result = parse_amass_output(path)
            assert len(result.subdomains) == 1
            assert len(result.ips) == 1
        finally:
            os.unlink(path)

    def test_graph_format_mixed_record_types(self) -> None:
        """Multiple record types from real Amass output."""
        path = _write_txt([
            "example.com (FQDN) --> a_record --> 93.184.216.34 (IPAddress)",
            "www.example.com (FQDN) --> cname_record --> example.com (FQDN)",
            "mail.example.com (FQDN) --> a_record --> 93.184.216.35 (IPAddress)",
            "ns1.example.com (FQDN) --> a_record --> 93.184.216.36 (IPAddress)",
        ])
        try:
            result = parse_amass_output(path)
            assert len(result.subdomains) == 4
            assert len(result.ips) == 3
        finally:
            os.unlink(path)
