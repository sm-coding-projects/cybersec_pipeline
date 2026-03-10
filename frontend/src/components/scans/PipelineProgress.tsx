import { Check, Loader2, Circle, X } from "lucide-react";
import { PHASE_SHORT_NAMES, PHASE_NAMES } from "@/utils/constants";
import { formatDuration } from "@/utils/formatters";

interface PhaseState {
  status: string; // pending | running | completed | failed | skipped
  duration_seconds: number | null;
}

interface PipelineProgressProps {
  phases: Record<number, PhaseState>;
  currentPhase: number;
  className?: string;
}

function getPhaseStatusClasses(status: string): {
  bg: string;
  border: string;
  text: string;
  label: string;
} {
  switch (status) {
    case "running":
      return {
        bg: "bg-accent/10",
        border: "border-accent animate-pulse",
        text: "text-accent",
        label: "text-accent",
      };
    case "completed":
      return {
        bg: "bg-success/10",
        border: "border-success",
        text: "text-success",
        label: "text-success",
      };
    case "failed":
      return {
        bg: "bg-severity-critical/10",
        border: "border-severity-critical",
        text: "text-severity-critical",
        label: "text-severity-critical",
      };
    case "skipped":
      return {
        bg: "bg-surface",
        border: "border-border",
        text: "text-text-muted",
        label: "text-text-muted",
      };
    default: // pending
      return {
        bg: "bg-surface",
        border: "border-border",
        text: "text-text-muted",
        label: "text-text-muted",
      };
  }
}

function PhaseStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "running":
      return <Loader2 className="h-5 w-5 text-accent animate-spin" />;
    case "completed":
      return <Check className="h-5 w-5 text-success" />;
    case "failed":
      return <X className="h-5 w-5 text-severity-critical" />;
    default:
      return <Circle className="h-4 w-4 text-text-muted" />;
  }
}

function ConnectorArrow({ status }: { status: string }) {
  const color =
    status === "completed"
      ? "text-success"
      : status === "running"
        ? "text-accent"
        : "text-border";

  return (
    <div className={`flex items-center ${color}`}>
      <div className="w-6 h-px bg-current" />
      <svg className="h-3 w-3 -ml-0.5" fill="currentColor" viewBox="0 0 12 12">
        <path d="M2 1l8 5-8 5V1z" />
      </svg>
    </div>
  );
}

export default function PipelineProgress({
  phases,
  currentPhase,
  className = "",
}: PipelineProgressProps) {
  const phaseNumbers = [1, 2, 3, 4];

  return (
    <div className={`flex items-center justify-center gap-0 ${className}`}>
      {phaseNumbers.map((num, index) => {
        const phase = phases[num] || { status: "pending", duration_seconds: null };
        const styles = getPhaseStatusClasses(phase.status);
        const isActive = num === currentPhase;

        return (
          <div key={num} className="flex items-center">
            {/* Phase box */}
            <div
              className={`
                relative flex flex-col items-center justify-center
                w-28 h-24 rounded-lg border-2 transition-all duration-500
                ${styles.bg} ${styles.border}
                ${isActive ? "shadow-lg shadow-accent/20" : ""}
              `}
            >
              {/* Phase label */}
              <span
                className={`text-[10px] font-mono font-bold uppercase tracking-widest ${styles.label}`}
              >
                {PHASE_SHORT_NAMES[num] || `PHASE ${num}`}
              </span>

              {/* Status icon */}
              <div className="my-1.5">
                <PhaseStatusIcon status={phase.status} />
              </div>

              {/* Duration or status text */}
              <span className={`text-[10px] font-mono ${styles.text}`}>
                {phase.status === "completed" && phase.duration_seconds != null
                  ? formatDuration(phase.duration_seconds)
                  : phase.status === "running"
                    ? "running"
                    : phase.status === "failed"
                      ? "failed"
                      : phase.status === "skipped"
                        ? "skipped"
                        : "pending"}
              </span>

              {/* Phase full name tooltip on hover */}
              <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap">
                <span className="text-[9px] font-mono text-text-muted">
                  {PHASE_NAMES[num]}
                </span>
              </div>
            </div>

            {/* Connector arrow (except after the last phase) */}
            {index < phaseNumbers.length - 1 && (
              <ConnectorArrow
                status={
                  phase.status === "completed"
                    ? "completed"
                    : phase.status === "running"
                      ? "running"
                      : "pending"
                }
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
