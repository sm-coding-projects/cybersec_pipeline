#!/usr/bin/env python3
"""
nmap2json.py — Convert Nmap XML output to JSON format.

Usage:
    python3 nmap2json.py input.xml [output.json]

If output file is not specified, prints JSON to stdout.
"""

import json
import sys
import xml.etree.ElementTree as ET
from typing import Any


def parse_nmap_xml(xml_path: str) -> dict[str, Any]:
    """Parse an Nmap XML output file into a structured dictionary."""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as e:
        return {"error": f"Failed to parse XML: {e}", "hosts": []}

    root = tree.getroot()

    result: dict[str, Any] = {
        "scanner": root.get("scanner", "nmap"),
        "args": root.get("args", ""),
        "start_time": root.get("start", ""),
        "start_str": root.get("startstr", ""),
        "version": root.get("version", ""),
        "hosts": [],
    }

    # Parse scan info
    scaninfo = root.find("scaninfo")
    if scaninfo is not None:
        result["scan_info"] = {
            "type": scaninfo.get("type", ""),
            "protocol": scaninfo.get("protocol", ""),
            "num_services": scaninfo.get("numservices", ""),
            "services": scaninfo.get("services", ""),
        }

    # Parse each host
    for host_elem in root.findall("host"):
        host = parse_host(host_elem)
        result["hosts"].append(host)

    # Parse run stats
    runstats = root.find("runstats")
    if runstats is not None:
        finished = runstats.find("finished")
        hosts_stat = runstats.find("hosts")
        result["run_stats"] = {
            "finished_time": finished.get("time", "") if finished is not None else "",
            "finished_str": finished.get("timestr", "") if finished is not None else "",
            "elapsed": finished.get("elapsed", "") if finished is not None else "",
            "exit_status": finished.get("exit", "") if finished is not None else "",
            "hosts_up": hosts_stat.get("up", "0") if hosts_stat is not None else "0",
            "hosts_down": hosts_stat.get("down", "0") if hosts_stat is not None else "0",
            "hosts_total": hosts_stat.get("total", "0") if hosts_stat is not None else "0",
        }

    return result


def parse_host(host_elem: ET.Element) -> dict[str, Any]:
    """Parse a single host element from Nmap XML."""
    host: dict[str, Any] = {
        "status": "",
        "addresses": [],
        "hostnames": [],
        "ports": [],
        "os_matches": [],
    }

    # Host status
    status = host_elem.find("status")
    if status is not None:
        host["status"] = status.get("state", "unknown")
        host["status_reason"] = status.get("reason", "")

    # Addresses (IPv4, IPv6, MAC)
    for addr in host_elem.findall("address"):
        host["addresses"].append({
            "addr": addr.get("addr", ""),
            "addrtype": addr.get("addrtype", ""),
            "vendor": addr.get("vendor", ""),
        })

    # Hostnames
    hostnames_elem = host_elem.find("hostnames")
    if hostnames_elem is not None:
        for hostname in hostnames_elem.findall("hostname"):
            host["hostnames"].append({
                "name": hostname.get("name", ""),
                "type": hostname.get("type", ""),
            })

    # Ports
    ports_elem = host_elem.find("ports")
    if ports_elem is not None:
        for port_elem in ports_elem.findall("port"):
            port = parse_port(port_elem)
            host["ports"].append(port)

    # OS detection
    os_elem = host_elem.find("os")
    if os_elem is not None:
        for osmatch in os_elem.findall("osmatch"):
            os_match: dict[str, Any] = {
                "name": osmatch.get("name", ""),
                "accuracy": osmatch.get("accuracy", ""),
                "os_classes": [],
            }
            for osclass in osmatch.findall("osclass"):
                os_match["os_classes"].append({
                    "type": osclass.get("type", ""),
                    "vendor": osclass.get("vendor", ""),
                    "osfamily": osclass.get("osfamily", ""),
                    "osgen": osclass.get("osgen", ""),
                    "accuracy": osclass.get("accuracy", ""),
                })
            host["os_matches"].append(os_match)

    # Uptime
    uptime = host_elem.find("uptime")
    if uptime is not None:
        host["uptime"] = {
            "seconds": uptime.get("seconds", ""),
            "lastboot": uptime.get("lastboot", ""),
        }

    return host


def parse_port(port_elem: ET.Element) -> dict[str, Any]:
    """Parse a single port element from Nmap XML."""
    port: dict[str, Any] = {
        "port_id": int(port_elem.get("portid", "0")),
        "protocol": port_elem.get("protocol", ""),
    }

    # Port state
    state = port_elem.find("state")
    if state is not None:
        port["state"] = state.get("state", "")
        port["state_reason"] = state.get("reason", "")

    # Service detection
    service = port_elem.find("service")
    if service is not None:
        port["service"] = {
            "name": service.get("name", ""),
            "product": service.get("product", ""),
            "version": service.get("version", ""),
            "extra_info": service.get("extrainfo", ""),
            "os_type": service.get("ostype", ""),
            "method": service.get("method", ""),
            "conf": service.get("conf", ""),
        }

        # CPE entries
        cpes = service.findall("cpe")
        if cpes:
            port["service"]["cpe"] = [cpe.text for cpe in cpes if cpe.text]

    # Script output
    scripts = port_elem.findall("script")
    if scripts:
        port["scripts"] = []
        for script in scripts:
            port["scripts"].append({
                "id": script.get("id", ""),
                "output": script.get("output", ""),
            })

    return port


def main() -> None:
    """Main entry point for CLI usage."""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <input.xml> [output.json]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    result = parse_nmap_xml(input_path)
    json_output = json.dumps(result, indent=2)

    if output_path:
        with open(output_path, "w") as f:
            f.write(json_output)
        print(f"Converted {input_path} -> {output_path}", file=sys.stderr)
    else:
        print(json_output)


if __name__ == "__main__":
    main()
