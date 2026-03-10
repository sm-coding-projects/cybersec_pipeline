import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Search, Filter, ShieldAlert } from "lucide-react";
import { useFindings } from "@/api/findings";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import { Pagination } from "@/components/common/Table";
import FindingsTable from "@/components/findings/FindingsTable";
import { Severity, FindingStatus } from "@/types/finding";

const SEVERITY_OPTIONS = [
  { value: "", label: "All Severities" },
  { value: Severity.CRITICAL, label: "Critical" },
  { value: Severity.HIGH, label: "High" },
  { value: Severity.MEDIUM, label: "Medium" },
  { value: Severity.LOW, label: "Low" },
  { value: Severity.INFO, label: "Info" },
];

const STATUS_OPTIONS = [
  { value: "", label: "All Statuses" },
  { value: FindingStatus.OPEN, label: "Open" },
  { value: FindingStatus.CONFIRMED, label: "Confirmed" },
  { value: FindingStatus.FALSE_POSITIVE, label: "False Positive" },
  { value: FindingStatus.RESOLVED, label: "Resolved" },
];

const SOURCE_TOOL_OPTIONS = [
  { value: "", label: "All Tools" },
  { value: "nuclei", label: "Nuclei" },
  { value: "zap", label: "ZAP" },
  { value: "nmap", label: "Nmap" },
  { value: "nmap-scanner", label: "Nmap Scanner" },
  { value: "openvas", label: "OpenVAS" },
];

export default function Findings() {
  const [searchParams] = useSearchParams();
  const scanIdParam = searchParams.get("scanId");

  const [page, setPage] = useState(1);
  const [severity, setSeverity] = useState("");
  const [sourceTool, setSourceTool] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  const perPage = 20;

  const { data, isLoading, isError } = useFindings({
    page,
    perPage,
    severity: severity || undefined,
    sourceTool: sourceTool || undefined,
    status: status || undefined,
    search: search || undefined,
    sortBy,
    sortOrder,
    scanId: scanIdParam ? parseInt(scanIdParam, 10) : undefined,
  });

  function handleSort(key: string, order: "asc" | "desc") {
    setSortBy(key);
    setSortOrder(order);
    setPage(1);
  }

  function handleFilterChange(setter: (val: string) => void) {
    return (val: string) => {
      setter(val);
      setPage(1);
    };
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-mono font-bold text-text-primary tracking-wide flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-accent" />
          Findings
        </h1>
        <p className="text-text-muted text-xs font-mono mt-1">
          {data?.total ?? 0} total findings
          {scanIdParam ? ` for scan #${scanIdParam}` : ""}
        </p>
      </div>

      {/* Filter toolbar */}
      <div className="bg-surface border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <Filter className="h-4 w-4 text-text-muted" />
          <span className="text-[10px] font-mono font-bold text-text-muted uppercase tracking-widest">
            Filters
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {/* Search input */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-muted" />
            <input
              type="text"
              value={search}
              onChange={(e) => handleFilterChange(setSearch)(e.target.value)}
              placeholder="Search findings..."
              className="w-full bg-background border border-border rounded pl-9 pr-3 py-2 text-xs font-mono text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
            />
          </div>

          {/* Severity dropdown */}
          <select
            value={severity}
            onChange={(e) => handleFilterChange(setSeverity)(e.target.value)}
            className="bg-background border border-border rounded px-3 py-2 text-xs font-mono text-text-secondary focus:outline-none focus:border-accent transition-colors"
          >
            {SEVERITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          {/* Source tool dropdown */}
          <select
            value={sourceTool}
            onChange={(e) => handleFilterChange(setSourceTool)(e.target.value)}
            className="bg-background border border-border rounded px-3 py-2 text-xs font-mono text-text-secondary focus:outline-none focus:border-accent transition-colors"
          >
            {SOURCE_TOOL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          {/* Status dropdown */}
          <select
            value={status}
            onChange={(e) => handleFilterChange(setStatus)(e.target.value)}
            className="bg-background border border-border rounded px-3 py-2 text-xs font-mono text-text-secondary focus:outline-none focus:border-accent transition-colors"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center justify-center h-48">
          <LoadingSpinner size="lg" />
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="bg-severity-critical/10 border border-severity-critical/30 rounded-lg p-4">
          <p className="text-sm font-mono text-severity-critical">
            Failed to load findings. Please try again.
          </p>
        </div>
      )}

      {/* Table */}
      {!isLoading && !isError && (
        <div className="bg-surface border border-border rounded-lg overflow-hidden">
          <FindingsTable
            findings={data?.items || []}
            sortBy={sortBy}
            sortOrder={sortOrder}
            onSort={handleSort}
            emptyMessage="No findings match your filters."
          />
          <div className="px-4 pb-3">
            <Pagination
              page={data?.page ?? 1}
              totalPages={data?.pages ?? 1}
              onPageChange={setPage}
            />
          </div>
        </div>
      )}
    </div>
  );
}
