import { useNavigate } from "react-router-dom";
import { ExternalLink, Server, Globe } from "lucide-react";
import Card from "@/components/common/Card";
import Badge from "@/components/common/Badge";
import { SeverityBadge } from "@/components/common/Badge";
import { TOOL_NAMES } from "@/utils/constants";
import { getRelativeTime } from "@/utils/formatters";
import type { Finding } from "@/types/finding";

interface FindingCardProps {
  finding: Finding;
  className?: string;
}

export default function FindingCard({ finding, className = "" }: FindingCardProps) {
  const navigate = useNavigate();

  return (
    <Card
      hover
      onClick={() => navigate(`/findings/${finding.id}`)}
      className={className}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <SeverityBadge severity={finding.severity} />
          <h3 className="text-sm font-mono font-medium text-text-primary truncate">
            {finding.title}
          </h3>
        </div>
        <Badge variant="status">{finding.status}</Badge>
      </div>

      <div className="flex items-center gap-4 text-xs font-mono text-text-muted">
        <span className="flex items-center gap-1">
          <Server className="h-3 w-3" />
          {TOOL_NAMES[finding.source_tool] || finding.source_tool}
        </span>
        {finding.affected_host && (
          <span className="flex items-center gap-1 truncate">
            <Globe className="h-3 w-3" />
            {finding.affected_host}
            {finding.affected_port ? `:${finding.affected_port}` : ""}
          </span>
        )}
        {finding.affected_url && (
          <span className="flex items-center gap-1 truncate">
            <ExternalLink className="h-3 w-3" />
            {finding.affected_url}
          </span>
        )}
        <span className="ml-auto flex-shrink-0">
          {getRelativeTime(finding.created_at)}
        </span>
      </div>

      {finding.description && (
        <p className="mt-2 text-xs text-text-secondary line-clamp-2">
          {finding.description}
        </p>
      )}
    </Card>
  );
}
