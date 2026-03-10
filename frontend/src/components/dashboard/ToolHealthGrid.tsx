import type { ToolStatus } from "@/types/api";
import Card from "@/components/common/Card";
import { TOOL_NAMES } from "@/utils/constants";

interface ToolHealthGridProps {
  tools: ToolStatus[];
  compact?: boolean;
  className?: string;
}

export default function ToolHealthGrid({ tools, compact = false, className = "" }: ToolHealthGridProps) {
  return (
    <div className={className}>
      {!compact && (
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-text-primary font-mono uppercase tracking-wider">
            Container Health
          </h3>
        </div>
      )}
      <div className={`grid gap-3 ${compact ? "grid-cols-2 lg:grid-cols-3" : "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"}`}>
        {tools.map((tool) => (
          <ToolHealthCard key={tool.container} tool={tool} compact={compact} />
        ))}
      </div>
    </div>
  );
}

interface ToolHealthCardProps {
  tool: ToolStatus;
  compact: boolean;
}

function ToolHealthCard({ tool, compact }: ToolHealthCardProps) {
  const displayName = TOOL_NAMES[tool.name] || tool.name;

  return (
    <Card className="relative">
      <div className="flex items-start gap-3">
        {/* Status dot */}
        <span
          className={`flex-shrink-0 mt-1 w-2.5 h-2.5 rounded-full ${
            tool.running
              ? "bg-success shadow-[0_0_6px_rgba(16,185,129,0.5)]"
              : "bg-severity-critical shadow-[0_0_6px_rgba(239,68,68,0.5)]"
          }`}
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-mono font-medium text-text-primary truncate">
            {displayName}
          </p>
          <p className="text-xs font-mono text-text-muted mt-0.5">
            {tool.container}
          </p>
          {!compact && (
            <div className="mt-2 space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-text-muted uppercase">
                  Status
                </span>
                <span
                  className={`text-xs font-mono font-medium ${
                    tool.running ? "text-success" : "text-severity-critical"
                  }`}
                >
                  {tool.running ? "Running" : "Stopped"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-text-muted uppercase">
                  Uptime
                </span>
                <span className="text-xs font-mono text-text-secondary">
                  {tool.uptime || "--"}
                </span>
              </div>
              {tool.api_reachable !== undefined && (
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono text-text-muted uppercase">
                    API
                  </span>
                  <span
                    className={`text-xs font-mono font-medium ${
                      tool.api_reachable ? "text-success" : "text-severity-critical"
                    }`}
                  >
                    {tool.api_reachable ? "Reachable" : "Unreachable"}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
