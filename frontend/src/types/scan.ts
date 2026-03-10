export enum ScanStatus {
  PENDING = "pending",
  RUNNING = "running",
  COMPLETED = "completed",
  FAILED = "failed",
  CANCELLED = "cancelled",
}

export enum PhaseStatus {
  PENDING = "pending",
  RUNNING = "running",
  COMPLETED = "completed",
  FAILED = "failed",
  SKIPPED = "skipped",
}

export interface ScanPhase {
  id: number;
  scan_id: number;
  phase_number: number;
  phase_name: string;
  status: PhaseStatus;
  tool_statuses: Record<string, string>;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  error_message: string | null;
  log_output: string | null;
}

export interface ScanConfig {
  harvester_sources?: string;
  amass_timeout_minutes?: number;
  masscan_rate?: number;
  masscan_ports?: string;
  nmap_scripts?: string;
  nuclei_severity?: string[];
  nuclei_rate_limit?: number;
  enable_zap?: boolean;
  enable_openvas?: boolean;
  push_to_defectdojo?: boolean;
}

export interface Scan {
  id: number;
  scan_uid: string;
  target_domain: string;
  status: ScanStatus;
  current_phase: number;
  config: ScanConfig;
  results_dir: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  created_by: number;
  created_at: string;
  updated_at: string;
  phases: ScanPhase[];
}

export interface ScanCreate {
  target_domain: string;
  config?: ScanConfig;
}
