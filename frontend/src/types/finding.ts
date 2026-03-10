export enum Severity {
  CRITICAL = "critical",
  HIGH = "high",
  MEDIUM = "medium",
  LOW = "low",
  INFO = "info",
}

export enum FindingStatus {
  OPEN = "open",
  CONFIRMED = "confirmed",
  FALSE_POSITIVE = "false_positive",
  RESOLVED = "resolved",
}

export interface Finding {
  id: number;
  scan_id: number;
  target_id: number | null;
  title: string;
  severity: Severity;
  source_tool: string;
  template_id: string | null;
  description: string;
  evidence: string | null;
  remediation: string | null;
  reference_urls: string[];
  affected_url: string | null;
  affected_host: string | null;
  affected_port: number | null;
  status: FindingStatus;
  is_duplicate: boolean;
  defectdojo_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface FindingUpdate {
  status?: FindingStatus;
  is_duplicate?: boolean;
}

export interface DashboardStats {
  total_scans: number;
  active_scans: number;
  total_findings: number;
  critical_findings: number;
  high_findings: number;
  medium_findings: number;
  low_findings: number;
  info_findings: number;
  total_targets_discovered: number;
  unique_ips: number;
  unique_subdomains: number;
}

export interface SeverityBreakdown {
  severity: Severity;
  count: number;
}

export interface ScanTimelineEntry {
  id: number;
  target_domain: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  finding_count: number;
}
