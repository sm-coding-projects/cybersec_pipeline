import { useNavigate } from "react-router-dom";
import Table, { type Column } from "@/components/common/Table";
import Badge from "@/components/common/Badge";
import { SeverityBadge } from "@/components/common/Badge";
import { TOOL_NAMES } from "@/utils/constants";
import { formatDateShort } from "@/utils/formatters";
import type { Finding } from "@/types/finding";

interface FindingsTableProps {
  findings: Finding[];
  sortBy?: string;
  sortOrder?: "asc" | "desc";
  onSort?: (key: string, order: "asc" | "desc") => void;
  emptyMessage?: string;
  className?: string;
}

export default function FindingsTable({
  findings,
  sortBy,
  sortOrder,
  onSort,
  emptyMessage = "No findings found",
  className = "",
}: FindingsTableProps) {
  const navigate = useNavigate();

  const columns: Column<Finding>[] = [
    {
      key: "severity",
      header: "Severity",
      sortable: true,
      className: "w-24",
      render: (finding) => <SeverityBadge severity={finding.severity} />,
    },
    {
      key: "title",
      header: "Title",
      sortable: true,
      render: (finding) => (
        <span className="font-mono text-sm text-text-primary">
          {finding.title}
        </span>
      ),
    },
    {
      key: "source_tool",
      header: "Source",
      sortable: true,
      className: "w-28",
      render: (finding) => (
        <span className="font-mono text-xs text-text-secondary">
          {TOOL_NAMES[finding.source_tool] || finding.source_tool}
        </span>
      ),
    },
    {
      key: "affected_host",
      header: "Target",
      sortable: true,
      render: (finding) => (
        <span className="font-mono text-xs text-text-secondary truncate max-w-[200px] block">
          {finding.affected_url ||
            (finding.affected_host
              ? `${finding.affected_host}${finding.affected_port ? `:${finding.affected_port}` : ""}`
              : "--")}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      className: "w-28",
      render: (finding) => <Badge variant="status">{finding.status}</Badge>,
    },
    {
      key: "scan_id",
      header: "Scan",
      sortable: true,
      className: "w-16",
      render: (finding) => (
        <span className="font-mono text-xs text-accent">
          #{finding.scan_id}
        </span>
      ),
    },
    {
      key: "created_at",
      header: "Date",
      sortable: true,
      className: "w-28",
      render: (finding) => (
        <span className="font-mono text-xs text-text-muted">
          {formatDateShort(finding.created_at)}
        </span>
      ),
    },
  ];

  return (
    <Table
      columns={columns}
      data={findings}
      onRowClick={(finding) => navigate(`/findings/${finding.id}`)}
      sortBy={sortBy}
      sortOrder={sortOrder}
      onSort={onSort}
      emptyMessage={emptyMessage}
      className={className}
    />
  );
}
