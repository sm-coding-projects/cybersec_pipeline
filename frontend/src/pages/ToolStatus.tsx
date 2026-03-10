import { Server, RefreshCw } from "lucide-react";
import { useToolStatus } from "@/api/tools";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import ToolHealthGrid from "@/components/dashboard/ToolHealthGrid";

export default function ToolStatus() {
  const { data, isLoading, isError, dataUpdatedAt, refetch, isFetching } = useToolStatus();

  const tools = data?.tools || [];
  const runningCount = tools.filter((t) => t.running).length;
  const stoppedCount = tools.filter((t) => !t.running).length;

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "--";

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-mono font-bold text-text-primary tracking-wide flex items-center gap-2">
            <Server className="h-5 w-5 text-accent" />
            Tool Status
          </h1>
          <p className="text-text-muted text-xs font-mono mt-1">
            Container health monitoring -- auto-refreshes every 30s
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono rounded border border-border text-text-secondary hover:text-text-primary hover:bg-surface-elevated disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Summary bar */}
      <div className="flex items-center gap-6 text-xs font-mono">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-success" />
          <span className="text-text-secondary">
            {runningCount} Running
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-severity-critical" />
          <span className="text-text-secondary">
            {stoppedCount} Stopped
          </span>
        </div>
        <span className="text-text-muted">
          Last updated: {lastUpdated}
        </span>
      </div>

      {/* Error state */}
      {isError && (
        <div className="bg-severity-critical/10 border border-severity-critical/30 rounded-lg p-4">
          <p className="text-sm font-mono text-severity-critical">
            Failed to fetch tool status. The backend may be unreachable.
          </p>
        </div>
      )}

      {/* Tool grid */}
      {tools.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Server className="h-12 w-12 text-text-muted mb-4" />
          <p className="text-text-muted text-sm font-mono">No tool containers found</p>
          <p className="text-text-muted text-xs font-mono mt-1">
            Ensure Docker containers are running
          </p>
        </div>
      ) : (
        <ToolHealthGrid tools={tools} />
      )}
    </div>
  );
}
