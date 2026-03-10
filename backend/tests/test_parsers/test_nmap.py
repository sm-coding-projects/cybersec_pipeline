"""Tests for the Nmap XML output parser."""

from __future__ import annotations

import os
import tempfile

import pytest

from app.pipeline.parsers.nmap import NmapHost, NmapPort, parse_nmap_output

SAMPLE_NMAP_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nmaprun>
<nmaprun scanner="nmap" args="nmap -sV -p 80,443 scanme.nmap.org" start="1710000000">
  <host starttime="1710000001" endtime="1710000010">
    <status state="up" reason="syn-ack"/>
    <address addr="45.33.32.156" addrtype="ipv4"/>
    <hostnames>
      <hostname name="scanme.nmap.org" type="user"/>
    </hostnames>
    <ports>
      <port protocol="tcp" portid="80">
        <state state="open" reason="syn-ack"/>
        <service name="http" product="Apache httpd" version="2.4.7" extrainfo="(Ubuntu)"/>
      </port>
      <port protocol="tcp" portid="443">
        <state state="closed" reason="reset"/>
        <service name="https"/>
      </port>
    </ports>
  </host>
  <host starttime="1710000001" endtime="1710000010">
    <status state="down" reason="no-response"/>
    <address addr="10.0.0.1" addrtype="ipv4"/>
  </host>
</nmaprun>
"""


def _write_xml(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".xml")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


class TestParseNmapOutput:
    def test_valid_output(self) -> None:
        path = _write_xml(SAMPLE_NMAP_XML)
        try:
            hosts = parse_nmap_output(path)
            # Only the "up" host should be included
            assert len(hosts) == 1
            host = hosts[0]
            assert isinstance(host, NmapHost)
            assert host.ip == "45.33.32.156"
            assert host.hostname == "scanme.nmap.org"
            assert len(host.ports) == 2

            http_port = next(p for p in host.ports if p.port == 80)
            assert http_port.protocol == "tcp"
            assert http_port.state == "open"
            assert http_port.service == "http"
            assert "Apache httpd" in http_port.version
            assert "2.4.7" in http_port.version
        finally:
            os.unlink(path)

    def test_empty_xml(self) -> None:
        path = _write_xml('<?xml version="1.0"?><nmaprun></nmaprun>')
        try:
            hosts = parse_nmap_output(path)
            assert hosts == []
        finally:
            os.unlink(path)

    def test_file_not_found(self) -> None:
        hosts = parse_nmap_output("/nonexistent/file.xml")
        assert hosts == []

    def test_invalid_xml(self) -> None:
        path = _write_xml("this is not xml <<<>>>")
        try:
            hosts = parse_nmap_output(path)
            assert hosts == []
        finally:
            os.unlink(path)

    def test_host_without_ports(self) -> None:
        xml = """\
<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="10.0.0.1" addrtype="ipv4"/>
  </host>
</nmaprun>
"""
        path = _write_xml(xml)
        try:
            hosts = parse_nmap_output(path)
            assert len(hosts) == 1
            assert hosts[0].ports == []
        finally:
            os.unlink(path)

    def test_service_without_version(self) -> None:
        xml = """\
<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="10.0.0.1" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="22">
        <state state="open"/>
        <service name="ssh"/>
      </port>
    </ports>
  </host>
</nmaprun>
"""
        path = _write_xml(xml)
        try:
            hosts = parse_nmap_output(path)
            assert len(hosts) == 1
            port = hosts[0].ports[0]
            assert port.service == "ssh"
            assert port.version == ""
        finally:
            os.unlink(path)
