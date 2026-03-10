import { type ReactNode } from "react";
import { Severity } from "@/types/finding";
import { SEVERITY_BG_CLASSES } from "@/utils/constants";

type BadgeVariant = "severity" | "status" | "default";

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  severity?: Severity;
  className?: string;
}

const statusClasses: Record<string, string> = {
  running: "bg-accent/20 text-accent",
  completed: "bg-success/20 text-success",
  failed: "bg-severity-critical/20 text-severity-critical",
  pending: "bg-text-muted/20 text-text-muted",
  cancelled: "bg-severity-medium/20 text-severity-medium",
  open: "bg-severity-high/20 text-severity-high",
  confirmed: "bg-severity-critical/20 text-severity-critical",
  false_positive: "bg-text-muted/20 text-text-muted",
  resolved: "bg-success/20 text-success",
};

export default function Badge({
  children,
  variant = "default",
  severity,
  className = "",
}: BadgeProps) {
  let colorClasses = "bg-surface-elevated text-text-secondary";

  if (variant === "severity" && severity) {
    colorClasses = SEVERITY_BG_CLASSES[severity];
  } else if (variant === "status") {
    const status = typeof children === "string" ? children.toLowerCase() : "";
    colorClasses = statusClasses[status] || colorClasses;
  }

  return (
    <span
      className={`
        inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium uppercase tracking-wide
        ${colorClasses}
        ${className}
      `}
    >
      {children}
    </span>
  );
}

interface SeverityBadgeProps {
  severity: Severity;
  className?: string;
}

export function SeverityBadge({ severity, className = "" }: SeverityBadgeProps) {
  return (
    <Badge variant="severity" severity={severity} className={className}>
      {severity}
    </Badge>
  );
}
