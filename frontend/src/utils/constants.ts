import { Severity } from "@/types/finding";
import { PhaseStatus } from "@/types/scan";

export const SEVERITY_COLORS: Record<Severity, string> = {
  [Severity.CRITICAL]: "#ef4444",
  [Severity.HIGH]: "#f97316",
  [Severity.MEDIUM]: "#eab308",
  [Severity.LOW]: "#3b82f6",
  [Severity.INFO]: "#6b7280",
};

export const SEVERITY_BG_CLASSES: Record<Severity, string> = {
  [Severity.CRITICAL]: "bg-severity-critical text-white",
  [Severity.HIGH]: "bg-severity-high text-white",
  [Severity.MEDIUM]: "bg-severity-medium text-gray-900",
  [Severity.LOW]: "bg-severity-low text-white",
  [Severity.INFO]: "bg-severity-info text-white",
};

export const SEVERITY_ORDER: Severity[] = [
  Severity.CRITICAL,
  Severity.HIGH,
  Severity.MEDIUM,
  Severity.LOW,
  Severity.INFO,
];

export const PHASE_NAMES: Record<number, string> = {
  1: "Reconnaissance",
  2: "Network Scanning",
  3: "Vulnerability Scanning",
  4: "Reporting",
};

export const PHASE_SHORT_NAMES: Record<number, string> = {
  1: "RECON",
  2: "NETWORK",
  3: "VULNSCAN",
  4: "REPORT",
};

export const PHASE_STATUS_COLORS: Record<PhaseStatus, string> = {
  [PhaseStatus.PENDING]: "text-text-muted",
  [PhaseStatus.RUNNING]: "text-accent",
  [PhaseStatus.COMPLETED]: "text-success",
  [PhaseStatus.FAILED]: "text-severity-critical",
  [PhaseStatus.SKIPPED]: "text-text-muted",
};

export const TOOL_NAMES: Record<string, string> = {
  theharvester: "theHarvester",
  amass: "Amass",
  dnsx: "dnsx",
  masscan: "Masscan",
  "nmap-scanner": "Nmap",
  nmap: "Nmap",
  httpx: "httpx",
  nuclei: "Nuclei",
  zap: "ZAP",
  openvas: "OpenVAS",
  defectdojo: "DefectDojo",
};

export const LOCAL_STORAGE_TOKEN_KEY = "cybersec_access_token";
