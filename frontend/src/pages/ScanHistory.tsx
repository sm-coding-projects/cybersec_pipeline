import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { History } from "lucide-react";
import { useScans } from "@/api/scans";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import Badge from "@/components/common/Badge";
import Table, { Pagination, type Column } from "@/components/common/Table";
import { formatDate, formatDurationFromDates } from "@/utils/formatters";
import { PHASE_NAMES } from "@/utils/constants";
import type { Scan } from "@/types/scan";
import { ScanStatus } from "@/types/scan";

export default function ScanHistory() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const perPage = 15;

  const { data, isLoading, isError } = useScans(page, perPage);

  const columns: Column<Scan>[] = [
    {
      key: "target_domain",
      header: "Target Domain",
      sortable: true,
      render: (scan) => (
        <span className="font-mono text-accent font-medium">{scan.target_domain}</span>
      ),
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      render: (scan) => (
        <div className="flex items-center gap-2">
          {scan.status === ScanStatus.RUNNING && (
            <span className="flex-shrink-0 w-2 h-2 rounded-full bg-accent animate-pulse" />
          )}
          <Badge variant="status">{scan.status}</Badge>
        </div>
      ),
    },
    {
      key: "current_phase",
      header: "Phase",
      sortable: true,
      render: (scan) => (
        <span className="font-mono text-text-secondary text-xs">
          {scan.status === ScanStatus.COMPLETED
            ? "Done"
            : scan.status === ScanStatus.FAILED
              ? "Failed"
              : `${scan.current_phase}/4 ${PHASE_NAMES[scan.current_phase] || ""}`}
        </span>
      ),
    },
    {
      key: "created_at",
      header: "Created",
      sortable: true,
      render: (scan) => (
        <span className="font-mono text-text-secondary text-xs">
          {formatDate(scan.created_at)}
        </span>
      ),
    },
    {
      key: "duration",
      header: "Duration",
      render: (scan) => (
        <span className="font-mono text-text-secondary text-xs">
          {formatDurationFromDates(scan.started_at, scan.completed_at)}
        </span>
      ),
    },
    {
      key: "findings",
      header: "Findings",
      render: (scan) => {
        // Sum up findings from phases or show --
        const totalFindings = scan.phases.reduce((sum, phase) => {
          const toolStatuses = phase.tool_statuses || {};
          return sum + Object.keys(toolStatuses).length;
        }, 0);
        return (
          <span className="font-mono text-text-secondary text-xs">
            {scan.status === ScanStatus.PENDING ? "--" : totalFindings || "--"}
          </span>
        );
      },
    },
  ];

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
            <History className="h-5 w-5 text-accent" />
            Scan History
          </h1>
          <p className="text-text-muted text-xs font-mono mt-1">
            {data?.total ?? 0} total scans
          </p>
        </div>
      </div>

      {/* Error state */}
      {isError && (
        <div className="bg-severity-critical/10 border border-severity-critical/30 rounded-lg p-4">
          <p className="text-sm font-mono text-severity-critical">
            Failed to load scans. Please try again.
          </p>
        </div>
      )}

      {/* Table */}
      <div className="bg-surface border border-border rounded-lg overflow-hidden">
        <Table
          columns={columns}
          data={data?.items || []}
          onRowClick={(scan) => navigate(`/scans/${scan.id}`)}
          emptyMessage="No scans found. Start a new scan to get started."
        />
        <div className="px-4 pb-3">
          <Pagination
            page={data?.page ?? 1}
            totalPages={data?.pages ?? 1}
            onPageChange={setPage}
          />
        </div>
      </div>
    </div>
  );
}
