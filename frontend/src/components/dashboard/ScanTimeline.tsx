import { useNavigate } from "react-router-dom";
import type { ScanTimelineEntry } from "@/types/finding";
import Card from "@/components/common/Card";
import { CardHeader, CardTitle } from "@/components/common/Card";
import Badge from "@/components/common/Badge";
import { getRelativeTime, formatDurationFromDates } from "@/utils/formatters";

interface ScanTimelineProps {
  entries: ScanTimelineEntry[];
  className?: string;
}

export default function ScanTimeline({ entries, className = "" }: ScanTimelineProps) {
  const navigate = useNavigate();

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Recent Scans</CardTitle>
      </CardHeader>
      <div className="space-y-1">
        {entries.length === 0 && (
          <p className="text-text-muted text-xs font-mono py-4 text-center">
            No scans yet
          </p>
        )}
        {entries.map((entry) => (
          <div
            key={entry.id}
            className="flex items-center justify-between px-3 py-2.5 rounded hover:bg-surface-elevated transition-colors cursor-pointer group"
            onClick={() => navigate(`/scans/${entry.id}`)}
            role="button"
            tabIndex={0}
          >
            <div className="flex items-center gap-3 min-w-0">
              {/* Status indicator dot */}
              <span
                className={`flex-shrink-0 w-2 h-2 rounded-full ${
                  entry.status === "running"
                    ? "bg-accent animate-pulse"
                    : entry.status === "completed"
                      ? "bg-success"
                      : entry.status === "failed"
                        ? "bg-severity-critical"
                        : "bg-text-muted"
                }`}
              />
              <span className="text-sm font-mono text-text-primary truncate group-hover:text-accent transition-colors">
                {entry.target_domain}
              </span>
            </div>
            <div className="flex items-center gap-3 flex-shrink-0">
              <Badge variant="status">{entry.status}</Badge>
              <span className="text-xs font-mono text-text-muted w-16 text-right">
                {entry.finding_count} finds
              </span>
              <span className="text-xs font-mono text-text-muted w-20 text-right">
                {entry.started_at
                  ? formatDurationFromDates(entry.started_at, entry.completed_at)
                  : "--"}
              </span>
              <span className="text-xs font-mono text-text-muted w-16 text-right">
                {entry.started_at ? getRelativeTime(entry.started_at) : "--"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
