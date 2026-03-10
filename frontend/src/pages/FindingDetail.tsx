import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ExternalLink,
  Server,
  Globe,
  Shield,
  FileCode2,
  BookOpen,
  Link2,
  Tag,
} from "lucide-react";
import { useFinding, useUpdateFinding } from "@/api/findings";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import { SeverityBadge } from "@/components/common/Badge";
import Card from "@/components/common/Card";
import { CardHeader, CardTitle } from "@/components/common/Card";
import { TOOL_NAMES } from "@/utils/constants";
import { formatDate } from "@/utils/formatters";
import { FindingStatus } from "@/types/finding";

const STATUS_OPTIONS = [
  { value: FindingStatus.OPEN, label: "Open" },
  { value: FindingStatus.CONFIRMED, label: "Confirmed" },
  { value: FindingStatus.FALSE_POSITIVE, label: "False Positive" },
  { value: FindingStatus.RESOLVED, label: "Resolved" },
];

export default function FindingDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const findingId = id ? parseInt(id, 10) : undefined;

  const { data: finding, isLoading, isError } = useFinding(findingId);
  const updateFinding = useUpdateFinding();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (isError || !finding) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate("/findings")}
          className="flex items-center gap-1.5 text-sm font-mono text-text-secondary hover:text-text-primary transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to findings
        </button>
        <div className="bg-severity-critical/10 border border-severity-critical/30 rounded-lg p-6 text-center">
          <p className="text-sm font-mono text-severity-critical">
            Finding not found or failed to load.
          </p>
        </div>
      </div>
    );
  }

  function handleStatusChange(newStatus: FindingStatus) {
    if (!findingId) return;
    updateFinding.mutate({ findingId, update: { status: newStatus } });
  }

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Back link */}
      <button
        onClick={() => navigate("/findings")}
        className="flex items-center gap-1.5 text-sm font-mono text-text-secondary hover:text-text-primary transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to findings
      </button>

      {/* Header */}
      <div>
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 flex-wrap">
              <SeverityBadge severity={finding.severity} />
              <h1 className="text-lg font-mono font-bold text-text-primary">
                {finding.title}
              </h1>
            </div>
            <div className="flex items-center gap-4 mt-2 flex-wrap">
              <span className="flex items-center gap-1 text-xs font-mono text-text-muted">
                <Server className="h-3 w-3" />
                {TOOL_NAMES[finding.source_tool] || finding.source_tool}
              </span>
              {finding.template_id && (
                <span className="flex items-center gap-1 text-xs font-mono text-text-muted">
                  <Tag className="h-3 w-3" />
                  {finding.template_id}
                </span>
              )}
              <span className="text-xs font-mono text-text-muted">
                Scan #{finding.scan_id}
              </span>
              <span className="text-xs font-mono text-text-muted">
                {formatDate(finding.created_at)}
              </span>
            </div>
          </div>

          {/* Status update */}
          <div className="flex flex-col items-end gap-1">
            <label className="text-[10px] font-mono text-text-muted uppercase tracking-wider">
              Status
            </label>
            <select
              value={finding.status}
              onChange={(e) => handleStatusChange(e.target.value as FindingStatus)}
              disabled={updateFinding.isPending}
              className="bg-background border border-border rounded px-3 py-1.5 text-xs font-mono text-text-primary focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Affected target info */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Globe className="h-4 w-4 text-accent" />
            <CardTitle>Affected Target</CardTitle>
          </div>
        </CardHeader>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {finding.affected_host && (
            <div>
              <span className="block text-[10px] font-mono text-text-muted uppercase tracking-wider mb-1">
                Host
              </span>
              <span className="text-sm font-mono text-text-primary">
                {finding.affected_host}
              </span>
            </div>
          )}
          {finding.affected_port != null && (
            <div>
              <span className="block text-[10px] font-mono text-text-muted uppercase tracking-wider mb-1">
                Port
              </span>
              <span className="text-sm font-mono text-text-primary">
                {finding.affected_port}
              </span>
            </div>
          )}
          {finding.affected_url && (
            <div className="sm:col-span-3">
              <span className="block text-[10px] font-mono text-text-muted uppercase tracking-wider mb-1">
                URL
              </span>
              <a
                href={finding.affected_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-mono text-accent hover:underline break-all flex items-center gap-1"
              >
                {finding.affected_url}
                <ExternalLink className="h-3 w-3 flex-shrink-0" />
              </a>
            </div>
          )}
          {!finding.affected_host && !finding.affected_url && (
            <p className="text-xs font-mono text-text-muted">
              No specific target information available.
            </p>
          )}
        </div>
      </Card>

      {/* Description */}
      {finding.description && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-accent" />
              <CardTitle>Description</CardTitle>
            </div>
          </CardHeader>
          <div className="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">
            {finding.description}
          </div>
        </Card>
      )}

      {/* Evidence */}
      {finding.evidence && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <FileCode2 className="h-4 w-4 text-accent" />
              <CardTitle>Evidence</CardTitle>
            </div>
          </CardHeader>
          <div className="bg-[#0a0e17] rounded-lg p-4 overflow-x-auto">
            <pre className="text-xs font-mono text-text-secondary whitespace-pre-wrap break-all leading-5">
              {finding.evidence}
            </pre>
          </div>
        </Card>
      )}

      {/* Remediation */}
      {finding.remediation && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Shield className="h-4 w-4 text-success" />
              <CardTitle>Remediation</CardTitle>
            </div>
          </CardHeader>
          <div className="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">
            {finding.remediation}
          </div>
        </Card>
      )}

      {/* Reference URLs */}
      {finding.reference_urls && finding.reference_urls.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Link2 className="h-4 w-4 text-accent" />
              <CardTitle>References</CardTitle>
            </div>
          </CardHeader>
          <div className="space-y-2">
            {finding.reference_urls.map((url, index) => (
              <a
                key={index}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm font-mono text-accent hover:underline break-all"
              >
                <ExternalLink className="h-3 w-3 flex-shrink-0" />
                {url}
              </a>
            ))}
          </div>
        </Card>
      )}

      {/* Metadata footer */}
      <Card>
        <div className="flex flex-wrap items-center gap-6 text-xs font-mono text-text-muted">
          <div>
            <span className="uppercase tracking-wider">Finding ID:</span>{" "}
            <span className="text-text-secondary">{finding.id}</span>
          </div>
          <div>
            <span className="uppercase tracking-wider">Duplicate:</span>{" "}
            <span className="text-text-secondary">
              {finding.is_duplicate ? "Yes" : "No"}
            </span>
          </div>
          {finding.defectdojo_id && (
            <div>
              <span className="uppercase tracking-wider">DefectDojo:</span>{" "}
              <span className="text-accent">#{finding.defectdojo_id}</span>
            </div>
          )}
          <div>
            <span className="uppercase tracking-wider">Created:</span>{" "}
            <span className="text-text-secondary">
              {formatDate(finding.created_at)}
            </span>
          </div>
          <div>
            <span className="uppercase tracking-wider">Updated:</span>{" "}
            <span className="text-text-secondary">
              {formatDate(finding.updated_at)}
            </span>
          </div>
        </div>
      </Card>
    </div>
  );
}
