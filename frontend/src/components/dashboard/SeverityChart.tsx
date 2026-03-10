import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { SEVERITY_COLORS } from "@/utils/constants";
import { Severity } from "@/types/finding";
import type { SeverityBreakdown } from "@/types/finding";
import Card from "@/components/common/Card";
import { CardHeader, CardTitle } from "@/components/common/Card";

interface SeverityChartProps {
  data: SeverityBreakdown[];
  className?: string;
}

const CHART_COLORS: Record<string, string> = {
  [Severity.CRITICAL]: SEVERITY_COLORS[Severity.CRITICAL],
  [Severity.HIGH]: SEVERITY_COLORS[Severity.HIGH],
  [Severity.MEDIUM]: SEVERITY_COLORS[Severity.MEDIUM],
  [Severity.LOW]: SEVERITY_COLORS[Severity.LOW],
  [Severity.INFO]: SEVERITY_COLORS[Severity.INFO],
};

interface CustomTooltipPayloadEntry {
  name: string;
  value: number;
  payload: {
    severity: string;
    count: number;
  };
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: CustomTooltipPayloadEntry[];
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (active && payload && payload.length > 0) {
    const item = payload[0];
    return (
      <div className="bg-surface-elevated border border-border rounded px-3 py-2 shadow-lg">
        <p className="text-text-primary text-xs font-mono uppercase">
          {item.payload.severity}
        </p>
        <p className="text-text-secondary text-xs font-mono">
          {item.value} findings
        </p>
      </div>
    );
  }
  return null;
}

export default function SeverityChart({ data, className = "" }: SeverityChartProps) {
  const total = data.reduce((sum, item) => sum + item.count, 0);

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Severity Breakdown</CardTitle>
      </CardHeader>
      <div className="flex items-center gap-6">
        <div className="w-48 h-48 relative">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={75}
                paddingAngle={2}
                dataKey="count"
                nameKey="severity"
                strokeWidth={0}
              >
                {data.map((entry) => (
                  <Cell
                    key={entry.severity}
                    fill={CHART_COLORS[entry.severity] || "#6b7280"}
                  />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
          {/* Center label */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="text-center">
              <p className="text-2xl font-mono font-bold text-text-primary">{total}</p>
              <p className="text-[10px] font-mono text-text-muted uppercase">Total</p>
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className="space-y-2 flex-1">
          {data.map((item) => (
            <div key={item.severity} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: CHART_COLORS[item.severity] || "#6b7280" }}
                />
                <span className="text-xs font-mono text-text-secondary uppercase">
                  {item.severity}
                </span>
              </div>
              <span className="text-xs font-mono text-text-primary font-medium">
                {item.count}
              </span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
