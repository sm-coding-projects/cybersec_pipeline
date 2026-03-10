import type { ScanConfig } from "@/types/scan";
import Card from "@/components/common/Card";
import { CardHeader, CardTitle } from "@/components/common/Card";
import { Settings } from "lucide-react";

interface ScanConfigFormProps {
  config: ScanConfig;
  className?: string;
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between py-1.5">
      <span className="text-xs font-mono text-text-muted uppercase tracking-wider">
        {label}
      </span>
      <span className="text-xs font-mono text-text-primary text-right max-w-[60%] break-words">
        {value}
      </span>
    </div>
  );
}

export default function ScanConfigForm({ config, className = "" }: ScanConfigFormProps) {
  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Settings className="h-4 w-4 text-accent" />
          <CardTitle>Scan Configuration</CardTitle>
        </div>
      </CardHeader>

      <div className="divide-y divide-border/50">
        {config.harvester_sources && (
          <ConfigRow
            label="Data Sources"
            value={config.harvester_sources.split(",").join(", ")}
          />
        )}
        {config.amass_timeout_minutes != null && (
          <ConfigRow
            label="Amass Timeout"
            value={`${config.amass_timeout_minutes} min`}
          />
        )}
        {config.masscan_rate != null && (
          <ConfigRow
            label="Masscan Rate"
            value={`${config.masscan_rate.toLocaleString()} pps`}
          />
        )}
        {config.masscan_ports && (
          <ConfigRow label="Port Range" value={config.masscan_ports} />
        )}
        {config.nmap_scripts && (
          <ConfigRow label="Nmap Scripts" value={config.nmap_scripts} />
        )}
        {config.nuclei_severity && config.nuclei_severity.length > 0 && (
          <ConfigRow
            label="Nuclei Severity"
            value={config.nuclei_severity.join(", ")}
          />
        )}
        {config.nuclei_rate_limit != null && (
          <ConfigRow
            label="Nuclei Rate Limit"
            value={`${config.nuclei_rate_limit} req/s`}
          />
        )}
        <ConfigRow
          label="ZAP Scan"
          value={config.enable_zap ? "Enabled" : "Disabled"}
        />
        <ConfigRow
          label="OpenVAS"
          value={config.enable_openvas ? "Enabled" : "Disabled"}
        />
        <ConfigRow
          label="DefectDojo Push"
          value={config.push_to_defectdojo ? "Enabled" : "Disabled"}
        />
      </div>
    </Card>
  );
}
