import { type ReactNode } from "react";
import Card from "@/components/common/Card";

interface StatCardProps {
  icon: ReactNode;
  value: number | string;
  label: string;
  trend?: {
    direction: "up" | "down" | "neutral";
    value: string;
  };
  accentColor?: string;
  className?: string;
}

const trendColors = {
  up: "text-severity-critical",
  down: "text-success",
  neutral: "text-text-muted",
};

const trendArrows = {
  up: "\u2191",
  down: "\u2193",
  neutral: "\u2192",
};

export default function StatCard({
  icon,
  value,
  label,
  trend,
  accentColor = "text-accent",
  className = "",
}: StatCardProps) {
  return (
    <Card className={`relative overflow-hidden ${className}`}>
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <p className="text-text-muted text-xs font-mono uppercase tracking-wider">
            {label}
          </p>
          <p className={`text-3xl font-mono font-bold ${accentColor}`}>
            {value}
          </p>
          {trend && (
            <p className={`text-xs font-mono ${trendColors[trend.direction]}`}>
              {trendArrows[trend.direction]} {trend.value}
            </p>
          )}
        </div>
        <div className={`${accentColor} opacity-40`}>{icon}</div>
      </div>
    </Card>
  );
}
