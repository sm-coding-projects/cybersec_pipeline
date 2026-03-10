import { Check, Loader2, AlertCircle, Circle, Clock } from "lucide-react";
import Card from "@/components/common/Card";
import { CardHeader, CardTitle } from "@/components/common/Card";
import { PHASE_NAMES, TOOL_NAMES } from "@/utils/constants";

interface PhaseCardProps {
  phaseNumber: number;
  phaseStatus?: string;
  toolStatuses: Record<string, string>;
  toolResults: Record<string, Record<string, unknown>>;
  className?: string;
}

function ToolStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "running":
      return <Loader2 className="h-4 w-4 text-accent animate-spin" />;
    case "completed":
      return <Check className="h-4 w-4 text-success" />;
    case "error":
      return <AlertCircle className="h-4 w-4 text-severity-critical" />;
    case "skipped":
      return <Circle className="h-3 w-3 text-text-muted opacity-50" />;
    default:
      return <Circle className="h-3 w-3 text-text-muted" />;
  }
}

function getToolStatusLabel(status: string): string {
  switch (status) {
    case "running":
      return "Running";
    case "completed":
      return "Completed";
    case "error":
      return "Error";
    case "skipped":
      return "Skipped";
    default:
      return "Queued";
  }
}

function getToolStatusColor(status: string): string {
  switch (status) {
    case "running":
      return "text-accent";
    case "completed":
      return "text-success";
    case "error":
      return "text-severity-critical";
    case "skipped":
      return "text-text-muted opacity-50";
    default:
      return "text-text-muted";
  }
}

// Which tools belong to which phase
const PHASE_TOOLS: Record<number, string[]> = {
  1: ["theharvester", "amass", "dnsx"],
  2: ["masscan", "nmap", "nmap-scanner", "httpx"],
  3: ["nuclei", "zap", "openvas"],
  4: ["defectdojo"],
};

function formatToolResultSummary(results: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(results)) {
    if (typeof value === "number") {
      parts.push(`${value} ${key}`);
    }
  }
  return parts.length > 0 ? parts.join(", ") : "";
}

export default function PhaseCard({
  phaseNumber,
  phaseStatus,
  toolStatuses,
  toolResults,
  className = "",
}: PhaseCardProps) {
  const phaseName = PHASE_NAMES[phaseNumber] || `Phase ${phaseNumber}`;
  const expectedTools = PHASE_TOOLS[phaseNumber] || [];

  // Build the list of tools to display: known phase tools + any extras from events
  const allToolKeys = new Set([
    ...expectedTools,
    ...Object.keys(toolStatuses).filter((t) => {
      // Only include tools that match this phase
      return expectedTools.includes(t) || !Object.values(PHASE_TOOLS).flat().includes(t);
    }),
  ]);

  // Filter to only tools that have a status or belong to this phase
  const displayTools = Array.from(allToolKeys).filter(
    (tool) => toolStatuses[tool] || expectedTools.includes(tool)
  );

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-accent" />
          <CardTitle>Phase {phaseNumber}: {phaseName}</CardTitle>
        </div>
      </CardHeader>

      {displayTools.length === 0 ? (
        <p className="text-xs font-mono text-text-muted py-2">
          Waiting for phase to start...
        </p>
      ) : (
        <div className="space-y-2">
          {displayTools.map((tool) => {
            const phaseIsDone = phaseStatus === "completed" || phaseStatus === "failed";
            const status = toolStatuses[tool] || (phaseIsDone ? "skipped" : "pending");
            const results = toolResults[tool];
            const resultSummary = results ? formatToolResultSummary(results) : "";

            return (
              <div
                key={tool}
                className="flex items-center gap-3 px-3 py-2 rounded bg-background/50"
              >
                <ToolStatusIcon status={status} />
                <span className="font-mono text-sm text-text-primary min-w-[100px]">
                  {TOOL_NAMES[tool] || tool}
                </span>
                <span
                  className={`text-xs font-mono ${getToolStatusColor(status)} min-w-[80px]`}
                >
                  {getToolStatusLabel(status)}
                </span>
                {resultSummary && (
                  <span className="text-xs font-mono text-text-secondary ml-auto">
                    {resultSummary}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
