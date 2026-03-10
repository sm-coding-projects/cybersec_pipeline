"""Tool output parsers.

Each parser reads raw output from a security tool and returns
typed Python dataclass objects.
"""

from app.pipeline.parsers.amass import AmassResult, parse_amass_output
from app.pipeline.parsers.harvester import HarvesterResult, parse_harvester_output
from app.pipeline.parsers.httpx import HttpxResult, parse_httpx_output
from app.pipeline.parsers.masscan import MasscanResult, parse_masscan_output
from app.pipeline.parsers.nmap import NmapHost, NmapPort, parse_nmap_output
from app.pipeline.parsers.nuclei import NucleiFinding, parse_nuclei_output
from app.pipeline.parsers.zap import ZapAlert, parse_zap_output

__all__ = [
    # Harvester
    "HarvesterResult",
    "parse_harvester_output",
    # Amass
    "AmassResult",
    "parse_amass_output",
    # Nmap
    "NmapHost",
    "NmapPort",
    "parse_nmap_output",
    # Masscan
    "MasscanResult",
    "parse_masscan_output",
    # httpx
    "HttpxResult",
    "parse_httpx_output",
    # Nuclei
    "NucleiFinding",
    "parse_nuclei_output",
    # ZAP
    "ZapAlert",
    "parse_zap_output",
]
