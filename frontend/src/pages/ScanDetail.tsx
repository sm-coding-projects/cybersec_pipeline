import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  XCircle,
  Globe,
  Network,
  Mail,
  Link2,
  MonitorDot,
  ShieldAlert,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useScan, useDeleteScan } from "@/api/scans";
import { useWebSocket } from "@/hooks/useWebSocket";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import Badge from "@/components/common/Badge";
import Button from "@/components/common/Button";
import Card from "@/components/common/Card";
import { CardHeader, CardTitle } from "@/components/common/Card";
import PipelineProgress from "@/components/scans/PipelineProgress";
import PhaseCard from "@/components/scans/PhaseCard";
import LogStream from "@/components/scans/LogStream";
import ScanConfigForm from "@/components/scans/ScanConfigForm";
import { ScanStatus } from "@/types/scan";
import { formatDate, formatDurationFromDates } from "@/utils/formatters";

export default function ScanDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const scanId = id ? parseInt(id, 10) : undefined;

  const { data: scan, isLoading, isError } = useScan(scanId);
  const deleteScan = useDeleteScan();

  const isActive =
    scan?.status === ScanStatus.RUNNING || scan?.status === ScanStatus.PENDING;

  const { isConnected, scanData } = useWebSocket({
    scanId,
    enabled: isActive,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (isError || !scan) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate("/scans")}
          className="flex items-center gap-1.5 text-sm font-mono text-text-secondary hover:text-text-primary transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to scans
        </button>
        <div className="bg-severity-critical/10 border border-severity-critical/30 rounded-lg p-6 text-center">
          <p className="text-sm font-mono text-severity-critical">
            Scan not found or failed to load.
          </p>
        </div>
      </div>
    );
  }

  // Build phase statuses from REST data + WebSocket live data
  const phaseStates: Record<number, { status: string; duration_seconds: number | null }> = {};
  for (let i = 1; i <= 4; i++) {
    const restPhase = scan.phases.find((p) => p.phase_number === i);
    const wsStatus = scanData.phase_statuses[i];
    const wsDuration = scanData.phase_durations[i];

    phaseStates[i] = {
      status: wsStatus || restPhase?.status || "pending",
      duration_seconds: wsDuration ?? restPhase?.duration_seconds ?? null,
    };
  }

  // Determine current phase from WebSocket or REST
  const currentPhase = scanData.current_phase || scan.current_phase || 1;

  // Merge tool statuses from REST + WS
  const currentRestPhase = scan.phases.find((p) => p.phase_number === currentPhase);
  const mergedToolStatuses: Record<string, string> = {
    ...(currentRestPhase?.tool_statuses || {}),
    ...scanData.tool_statuses,
  };

  // Asset counts: prefer WS live data if available, fall back to 0
  const assets = {
    subdomains: scanData.subdomains,
    ips: scanData.ips,
    emails: scanData.emails,
    web_urls: scanData.web_urls,
    open_ports: scanData.open_ports,
    findings: scanData.findings,
  };

  const isCompleted = scan.status === ScanStatus.COMPLETED;
  const isFailed = scan.status === ScanStatus.FAILED;

  async function handleCancel() {
    if (!scanId) return;
    if (!window.confirm("Are you sure you want to cancel this scan?")) return;
    try {
      await deleteScan.mutateAsync(scanId);
      navigate("/scans");
    } catch {
      // handled by React Query
    }
  }

  return (
    <div className="space-y-6">
      {/* Back link */}
      <button
        onClick={() => navigate("/scans")}
        className="flex items-center gap-1.5 text-sm font-mono text-text-secondary hover:text-text-primary transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to scans
      </button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-mono font-bold text-text-primary tracking-wide">
              {scan.target_domain}
            </h1>
            <Badge variant="status">{scan.status}</Badge>
            {isActive && (
              <span className="flex items-center gap-1.5 text-xs font-mono">
                {isConnected ? (
                  <>
                    <Wifi className="h-3.5 w-3.5 text-success" />
                    <span className="text-success">Live</span>
                  </>
                ) : (
                  <>
                    <WifiOff className="h-3.5 w-3.5 text-text-muted" />
                    <span className="text-text-muted">Connecting...</span>
                  </>
                )}
              </span>
            )}
          </div>
          <div className="flex items-center gap-4 mt-1">
            <span className="text-xs font-mono text-text-muted">
              Started: {formatDate(scan.started_at)}
            </span>
            {scan.completed_at && (
              <span className="text-xs font-mono text-text-muted">
                Duration: {formatDurationFromDates(scan.started_at, scan.completed_at)}
              </span>
            )}
            {isActive && scan.started_at && (
              <span className="text-xs font-mono text-text-muted">
                Elapsed: {formatDurationFromDates(scan.started_at, null)}
              </span>
            )}
          </div>
        </div>

        {isActive && (
          <Button
            variant="danger"
            size="sm"
            onClick={handleCancel}
            isLoading={deleteScan.isPending}
            className="gap-1.5"
          >
            <XCircle className="h-4 w-4" />
            Cancel Scan
          </Button>
        )}
      </div>

      {/* Error banner */}
      {(isFailed || scanData.error) && (
        <div className="bg-severity-critical/10 border border-severity-critical/30 rounded-lg p-4">
          <p className="text-sm font-mono text-severity-critical">
            {scanData.error || scan.error_message || "Scan failed"}
          </p>
        </div>
      )}

      {/* Pipeline Progress */}
      <Card>
        <CardHeader>
          <CardTitle>Pipeline Progress</CardTitle>
        </CardHeader>
        <div className="py-6">
          <PipelineProgress
            phases={phaseStates}
            currentPhase={currentPhase}
          />
        </div>
      </Card>

      {/* Current Phase + Discovered Assets */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Phase detail */}
        <div className="lg:col-span-2">
          <PhaseCard
            phaseNumber={currentPhase}
            toolStatuses={mergedToolStatuses}
            toolResults={scanData.tool_results}
          />
        </div>

        {/* Discovered assets */}
        <Card>
          <CardHeader>
            <CardTitle>Discovered Assets</CardTitle>
          </CardHeader>
          <div className="space-y-3">
            <AssetRow
              icon={<Globe className="h-4 w-4" />}
              label="Subdomains"
              count={assets.subdomains}
              color="text-cyan-400"
            />
            <AssetRow
              icon={<Network className="h-4 w-4" />}
              label="IPs"
              count={assets.ips}
              color="text-blue-400"
            />
            <AssetRow
              icon={<Link2 className="h-4 w-4" />}
              label="Web URLs"
              count={assets.web_urls}
              color="text-green-400"
            />
            <AssetRow
              icon={<Mail className="h-4 w-4" />}
              label="Emails"
              count={assets.emails}
              color="text-purple-400"
            />
            <AssetRow
              icon={<MonitorDot className="h-4 w-4" />}
              label="Open Ports"
              count={assets.open_ports}
              color="text-orange-400"
            />
            <div className="border-t border-border pt-3">
              <AssetRow
                icon={<ShieldAlert className="h-4 w-4" />}
                label="Findings"
                count={assets.findings}
                color="text-severity-critical"
              />
            </div>
          </div>
        </Card>
      </div>

      {/* Log Stream */}
      {(isActive || scanData.logs.length > 0) && (
        <LogStream logs={scanData.logs} />
      )}

      {/* Completed: Summary + Config */}
      {isCompleted && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Summary */}
          {scanData.summary && (
            <Card>
              <CardHeader>
                <CardTitle>Scan Summary</CardTitle>
              </CardHeader>
              <div className="space-y-2">
                {Object.entries(scanData.summary).map(([key, value]) => (
                  <div key={key} className="flex justify-between py-1">
                    <span className="text-xs font-mono text-text-muted capitalize">
                      {key.replace(/_/g, " ")}
                    </span>
                    <span className="text-xs font-mono text-text-primary">
                      {typeof value === "number"
                        ? value.toLocaleString()
                        : String(value)}
                    </span>
                  </div>
                ))}
              </div>
              <div className="mt-4 pt-3 border-t border-border">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => navigate(`/findings?scanId=${scan.id}`)}
                  className="w-full"
                >
                  View All Findings
                </Button>
              </div>
            </Card>
          )}

          {/* Scan config */}
          <ScanConfigForm config={scan.config} />
        </div>
      )}

      {/* Show config when not completed and no summary */}
      {!isCompleted && !scanData.summary && (
        <ScanConfigForm config={scan.config} />
      )}
    </div>
  );
}

function AssetRow({
  icon,
  label,
  count,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
  color: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <span className={color}>{icon}</span>
        <span className="text-xs font-mono text-text-secondary">{label}</span>
      </div>
      <span className={`text-sm font-mono font-bold ${count > 0 ? "text-text-primary" : "text-text-muted"}`}>
        {count > 0 ? count.toLocaleString() : "--"}
      </span>
    </div>
  );
}
