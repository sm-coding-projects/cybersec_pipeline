import {
  Activity,
  AlertTriangle,
  AlertOctagon,
  Shield,
  Target,
} from "lucide-react";
import { useDashboardStats, useSeverityBreakdown, useScanTimeline } from "@/api/dashboard";
import { useFindings } from "@/api/findings";
import { useScans } from "@/api/scans";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import Card from "@/components/common/Card";
import { CardHeader, CardTitle } from "@/components/common/Card";
import Badge, { SeverityBadge } from "@/components/common/Badge";
import StatCard from "@/components/dashboard/StatCard";
import SeverityChart from "@/components/dashboard/SeverityChart";
import ScanTimeline from "@/components/dashboard/ScanTimeline";
import { formatNumber, getRelativeTime } from "@/utils/formatters";
import { PHASE_NAMES } from "@/utils/constants";
import { ScanStatus } from "@/types/scan";
import type { Severity } from "@/types/finding";

export default function Dashboard() {
  const { data: stats, isLoading: statsLoading } = useDashboardStats();
  const { data: severityData, isLoading: severityLoading } = useSeverityBreakdown();
  const { data: timeline, isLoading: timelineLoading } = useScanTimeline();
  const { data: recentFindings, isLoading: findingsLoading } = useFindings({ perPage: 8 });
  const { data: scansData } = useScans(1, 10);

  const activeScans = scansData?.items.filter(
    (s) => s.status === ScanStatus.RUNNING || s.status === ScanStatus.PENDING
  ) || [];

  if (statsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-mono font-bold text-text-primary tracking-wide">
          Command Center
        </h1>
        <p className="text-text-muted text-xs font-mono mt-1">
          Security pipeline overview and monitoring
        </p>
      </div>

      {/* Row 1: Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<Target className="h-8 w-8" />}
          value={formatNumber(stats?.total_scans ?? 0)}
          label="Total Scans"
          accentColor="text-accent"
        />
        <StatCard
          icon={<AlertOctagon className="h-8 w-8" />}
          value={formatNumber(stats?.critical_findings ?? 0)}
          label="Critical"
          accentColor="text-severity-critical"
        />
        <StatCard
          icon={<AlertTriangle className="h-8 w-8" />}
          value={formatNumber(stats?.high_findings ?? 0)}
          label="High"
          accentColor="text-severity-high"
        />
        <StatCard
          icon={<Shield className="h-8 w-8" />}
          value={formatNumber(stats?.medium_findings ?? 0)}
          label="Medium"
          accentColor="text-severity-medium"
        />
      </div>

      {/* Row 2: Severity chart + Active scan progress */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Severity donut chart */}
        {severityLoading ? (
          <Card className="flex items-center justify-center h-64">
            <LoadingSpinner />
          </Card>
        ) : (
          <SeverityChart data={severityData || []} />
        )}

        {/* Active scan progress */}
        <Card>
          <CardHeader>
            <CardTitle>Active Scans</CardTitle>
          </CardHeader>
          {activeScans.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Activity className="h-8 w-8 text-text-muted mb-2" />
              <p className="text-text-muted text-xs font-mono">No active scans</p>
              <p className="text-text-muted text-[10px] font-mono mt-1">
                Start a new scan from the sidebar
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {activeScans.slice(0, 3).map((scan) => (
                <ActiveScanCard key={scan.id} scan={scan} />
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Row 3: Recent scans timeline + Recent findings */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Scan timeline */}
        {timelineLoading ? (
          <Card className="flex items-center justify-center h-48">
            <LoadingSpinner />
          </Card>
        ) : (
          <ScanTimeline entries={timeline || []} />
        )}

        {/* Recent findings */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Findings</CardTitle>
          </CardHeader>
          {findingsLoading ? (
            <div className="flex items-center justify-center py-8">
              <LoadingSpinner />
            </div>
          ) : !recentFindings?.items.length ? (
            <p className="text-text-muted text-xs font-mono py-4 text-center">
              No findings yet
            </p>
          ) : (
            <div className="space-y-1">
              {recentFindings.items.map((finding) => (
                <div
                  key={finding.id}
                  className="flex items-center gap-3 px-3 py-2 rounded hover:bg-surface-elevated transition-colors"
                >
                  <SeverityBadge severity={finding.severity as Severity} />
                  <span className="text-sm font-mono text-text-primary truncate flex-1">
                    {finding.title}
                  </span>
                  <span className="text-xs font-mono text-text-muted flex-shrink-0">
                    {finding.source_tool}
                  </span>
                  <span className="text-xs font-mono text-text-muted flex-shrink-0 w-16 text-right">
                    {getRelativeTime(finding.created_at)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

interface ActiveScanCardProps {
  scan: {
    id: number;
    target_domain: string;
    status: ScanStatus;
    current_phase: number;
    phases: Array<{
      phase_number: number;
      status: string;
      duration_seconds: number | null;
    }>;
    started_at: string | null;
  };
}

function ActiveScanCard({ scan }: ActiveScanCardProps) {
  const totalPhases = 4;
  const completedPhases = scan.phases.filter((p) => p.status === "completed").length;
  const progressPercent = Math.round((completedPhases / totalPhases) * 100);

  return (
    <div className="bg-surface-elevated border border-border rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-mono font-medium text-accent truncate">
          {scan.target_domain}
        </span>
        <Badge variant="status">{scan.status}</Badge>
      </div>
      <div className="flex items-center justify-between text-xs font-mono text-text-muted mb-2">
        <span>
          Phase {scan.current_phase}/{totalPhases} --{" "}
          {PHASE_NAMES[scan.current_phase] || "Unknown"}
        </span>
        <span>{progressPercent}%</span>
      </div>
      {/* Progress bar */}
      <div className="w-full bg-background rounded-full h-1.5">
        <div
          className="bg-accent h-1.5 rounded-full transition-all duration-500"
          style={{ width: `${progressPercent}%` }}
        />
      </div>
    </div>
  );
}
