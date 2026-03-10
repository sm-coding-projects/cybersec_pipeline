"""Parser for Nmap XML output.

Nmap's ``-oX`` flag produces an XML report.  This parser extracts host
information including IP addresses, hostnames, and discovered ports with
service/version details.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class NmapPort:
    """A single port discovered on a host."""

    port: int
    protocol: str
    state: str
    service: str
    version: str


@dataclass
class NmapHost:
    """A host with its discovered ports."""

    ip: str
    hostname: str
    ports: list[NmapPort] = field(default_factory=list)


def parse_nmap_output(filepath: str) -> list[NmapHost]:
    """Parse Nmap XML output file into a list of ``NmapHost`` objects.

    Handles missing elements, malformed XML, and empty files gracefully.
    """
    try:
        tree = ET.parse(filepath)
    except FileNotFoundError:
        logger.warning("Nmap output file not found: %s", filepath)
        return []
    except ET.ParseError as exc:
        logger.warning("Nmap output is not valid XML (%s): %s", filepath, exc)
        return []

    root = tree.getroot()
    hosts: list[NmapHost] = []

    for host_elem in root.findall("host"):
        # Skip hosts that are down
        status_elem = host_elem.find("status")
        if status_elem is not None and status_elem.get("state") != "up":
            continue

        # IP address
        ip = ""
        for addr_elem in host_elem.findall("address"):
            if addr_elem.get("addrtype") == "ipv4":
                ip = addr_elem.get("addr", "")
                break
        if not ip:
            # Fall back to any address
            addr_elem = host_elem.find("address")
            if addr_elem is not None:
                ip = addr_elem.get("addr", "")

        # Hostname
        hostname = ""
        hostnames_elem = host_elem.find("hostnames")
        if hostnames_elem is not None:
            hostname_elem = hostnames_elem.find("hostname")
            if hostname_elem is not None:
                hostname = hostname_elem.get("name", "")

        # Ports
        ports: list[NmapPort] = []
        ports_elem = host_elem.find("ports")
        if ports_elem is not None:
            for port_elem in ports_elem.findall("port"):
                try:
                    port_id = int(port_elem.get("portid", "0"))
                except (ValueError, TypeError):
                    continue

                protocol = port_elem.get("protocol", "tcp")

                state_elem = port_elem.find("state")
                state = state_elem.get("state", "unknown") if state_elem is not None else "unknown"

                service_elem = port_elem.find("service")
                service = ""
                version = ""
                if service_elem is not None:
                    service = service_elem.get("name", "")
                    version_parts = [
                        service_elem.get("product", ""),
                        service_elem.get("version", ""),
                        service_elem.get("extrainfo", ""),
                    ]
                    version = " ".join(p for p in version_parts if p).strip()

                ports.append(
                    NmapPort(
                        port=port_id,
                        protocol=protocol,
                        state=state,
                        service=service,
                        version=version,
                    )
                )

        hosts.append(NmapHost(ip=ip, hostname=hostname, ports=ports))

    logger.info("Parsed Nmap output: %d hosts, %d total ports", len(hosts), sum(len(h.ports) for h in hosts))
    return hosts
