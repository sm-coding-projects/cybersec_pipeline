import { Severity } from "@/types/finding";
import Badge from "@/components/common/Badge";

interface SeverityBadgeProps {
  severity: Severity;
  className?: string;
}

export default function SeverityBadge({ severity, className = "" }: SeverityBadgeProps) {
  return (
    <Badge variant="severity" severity={severity} className={className}>
      {severity}
    </Badge>
  );
}
