import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Rocket, Globe, Radar, Network, ShieldAlert, FileText } from "lucide-react";
import { useCreateScan } from "@/api/scans";
import type { ScanConfig, ScanCreate } from "@/types/scan";
import Card from "@/components/common/Card";
import { CardHeader, CardTitle } from "@/components/common/Card";
import Button from "@/components/common/Button";

const HARVESTER_SOURCES = [
  "bing",
  "crtsh",
  "dnsdumpster",
  "duckduckgo",
  "hackertarget",
  "otx",
  "rapiddns",
  "subdomaincenter",
  "threatminer",
  "urlscan",
  "virustotal",
];

const NUCLEI_SEVERITIES = ["critical", "high", "medium", "low", "info"];

const DEFAULT_CONFIG: ScanConfig = {
  harvester_sources: "crtsh,dnsdumpster,hackertarget,otx,rapiddns",
  amass_timeout_minutes: 10,
  masscan_rate: 1000,
  masscan_ports: "1-65535",
  nmap_scripts: "default,vuln",
  nuclei_severity: ["critical", "high", "medium"],
  nuclei_rate_limit: 150,
  enable_zap: true,
  enable_openvas: false,
  push_to_defectdojo: false,
};

export default function ScanNew() {
  const navigate = useNavigate();
  const createScan = useCreateScan();

  const [domain, setDomain] = useState("");
  const [config, setConfig] = useState<ScanConfig>({ ...DEFAULT_CONFIG });
  const [validationError, setValidationError] = useState("");

  function updateConfig<K extends keyof ScanConfig>(key: K, value: ScanConfig[K]) {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }

  function toggleHarvesterSource(source: string) {
    const current = (config.harvester_sources || "").split(",").filter(Boolean);
    const updated = current.includes(source)
      ? current.filter((s) => s !== source)
      : [...current, source];
    updateConfig("harvester_sources", updated.join(","));
  }

  function toggleNucleiSeverity(severity: string) {
    const current = config.nuclei_severity || [];
    const updated = current.includes(severity)
      ? current.filter((s) => s !== severity)
      : [...current, severity];
    updateConfig("nuclei_severity", updated);
  }

  function isHarvesterSourceActive(source: string): boolean {
    return (config.harvester_sources || "").split(",").includes(source);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setValidationError("");

    const trimmed = domain.trim();
    if (!trimmed) {
      setValidationError("Domain is required");
      return;
    }

    // Basic domain validation
    const domainRegex = /^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$/;
    if (!domainRegex.test(trimmed)) {
      setValidationError("Please enter a valid domain (e.g., example.com)");
      return;
    }

    const scanData: ScanCreate = {
      target_domain: trimmed,
      config,
    };

    try {
      const scan = await createScan.mutateAsync(scanData);
      navigate(`/scans/${scan.id}`);
    } catch {
      // Error handling is managed by React Query
    }
  }

  return (
    <div className="max-w-4xl">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-xl font-mono font-bold text-text-primary tracking-wide">
          New Scan
        </h1>
        <p className="text-text-muted text-xs font-mono mt-1">
          Configure and launch a cybersecurity assessment
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Target domain */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Globe className="h-4 w-4 text-accent" />
              <CardTitle>Target</CardTitle>
            </div>
          </CardHeader>
          <div>
            <label className="block text-xs font-mono text-text-muted uppercase tracking-wider mb-2">
              Domain
            </label>
            <input
              type="text"
              value={domain}
              onChange={(e) => {
                setDomain(e.target.value);
                setValidationError("");
              }}
              placeholder="example.com"
              className="w-full bg-background border border-border rounded px-4 py-2.5 text-sm font-mono text-text-primary placeholder-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 transition-colors"
            />
            {validationError && (
              <p className="mt-2 text-xs font-mono text-severity-critical">
                {validationError}
              </p>
            )}
          </div>
        </Card>

        {/* Recon Settings */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Radar className="h-4 w-4 text-accent" />
              <CardTitle>Recon Settings</CardTitle>
            </div>
          </CardHeader>
          <div className="space-y-4">
            {/* Data sources */}
            <div>
              <label className="block text-xs font-mono text-text-muted uppercase tracking-wider mb-2">
                theHarvester Data Sources
              </label>
              <div className="flex flex-wrap gap-2">
                {HARVESTER_SOURCES.map((source) => (
                  <button
                    key={source}
                    type="button"
                    onClick={() => toggleHarvesterSource(source)}
                    className={`px-3 py-1.5 text-xs font-mono rounded border transition-colors ${
                      isHarvesterSourceActive(source)
                        ? "bg-accent/15 text-accent border-accent/40"
                        : "bg-background text-text-muted border-border hover:border-text-muted hover:text-text-secondary"
                    }`}
                  >
                    {source}
                  </button>
                ))}
              </div>
            </div>

            {/* Amass timeout */}
            <div>
              <label className="block text-xs font-mono text-text-muted uppercase tracking-wider mb-2">
                Amass Timeout:{" "}
                <span className="text-text-primary">{config.amass_timeout_minutes} min</span>
              </label>
              <input
                type="range"
                min={1}
                max={60}
                value={config.amass_timeout_minutes || 10}
                onChange={(e) => updateConfig("amass_timeout_minutes", Number(e.target.value))}
                className="w-full h-1.5 bg-background rounded-full appearance-none cursor-pointer accent-accent"
              />
              <div className="flex justify-between text-[10px] font-mono text-text-muted mt-1">
                <span>1 min</span>
                <span>60 min</span>
              </div>
            </div>
          </div>
        </Card>

        {/* Network Settings */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Network className="h-4 w-4 text-accent" />
              <CardTitle>Network Settings</CardTitle>
            </div>
          </CardHeader>
          <div className="space-y-4">
            {/* Port range */}
            <div>
              <label className="block text-xs font-mono text-text-muted uppercase tracking-wider mb-2">
                Port Range
              </label>
              <div className="flex gap-2">
                {["1-1024", "1-10000", "1-65535"].map((range) => (
                  <button
                    key={range}
                    type="button"
                    onClick={() => updateConfig("masscan_ports", range)}
                    className={`px-3 py-1.5 text-xs font-mono rounded border transition-colors ${
                      config.masscan_ports === range
                        ? "bg-accent/15 text-accent border-accent/40"
                        : "bg-background text-text-muted border-border hover:border-text-muted hover:text-text-secondary"
                    }`}
                  >
                    {range}
                  </button>
                ))}
                <input
                  type="text"
                  value={["1-1024", "1-10000", "1-65535"].includes(config.masscan_ports || "")
                    ? ""
                    : config.masscan_ports || ""}
                  onChange={(e) => updateConfig("masscan_ports", e.target.value)}
                  placeholder="Custom range"
                  className="flex-1 bg-background border border-border rounded px-3 py-1.5 text-xs font-mono text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                />
              </div>
            </div>

            {/* Masscan rate */}
            <div>
              <label className="block text-xs font-mono text-text-muted uppercase tracking-wider mb-2">
                Masscan Rate:{" "}
                <span className="text-text-primary">{config.masscan_rate?.toLocaleString()} pps</span>
              </label>
              <input
                type="range"
                min={100}
                max={10000}
                step={100}
                value={config.masscan_rate || 1000}
                onChange={(e) => updateConfig("masscan_rate", Number(e.target.value))}
                className="w-full h-1.5 bg-background rounded-full appearance-none cursor-pointer accent-accent"
              />
              <div className="flex justify-between text-[10px] font-mono text-text-muted mt-1">
                <span>100 pps</span>
                <span>10,000 pps</span>
              </div>
            </div>

            {/* Nmap scripts */}
            <div>
              <label className="block text-xs font-mono text-text-muted uppercase tracking-wider mb-2">
                Nmap Scripts
              </label>
              <input
                type="text"
                value={config.nmap_scripts || ""}
                onChange={(e) => updateConfig("nmap_scripts", e.target.value)}
                placeholder="default,vuln"
                className="w-full bg-background border border-border rounded px-4 py-2.5 text-sm font-mono text-text-primary placeholder-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 transition-colors"
              />
            </div>
          </div>
        </Card>

        {/* Vulnerability Scanning */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-accent" />
              <CardTitle>Vulnerability Scanning</CardTitle>
            </div>
          </CardHeader>
          <div className="space-y-4">
            {/* Nuclei severity filter */}
            <div>
              <label className="block text-xs font-mono text-text-muted uppercase tracking-wider mb-2">
                Nuclei Severity Filter
              </label>
              <div className="flex flex-wrap gap-2">
                {NUCLEI_SEVERITIES.map((sev) => {
                  const isActive = (config.nuclei_severity || []).includes(sev);
                  const colorMap: Record<string, string> = {
                    critical: isActive ? "bg-severity-critical/20 text-severity-critical border-severity-critical/40" : "",
                    high: isActive ? "bg-severity-high/20 text-severity-high border-severity-high/40" : "",
                    medium: isActive ? "bg-severity-medium/20 text-severity-medium border-severity-medium/40" : "",
                    low: isActive ? "bg-severity-low/20 text-severity-low border-severity-low/40" : "",
                    info: isActive ? "bg-severity-info/20 text-severity-info border-severity-info/40" : "",
                  };
                  return (
                    <button
                      key={sev}
                      type="button"
                      onClick={() => toggleNucleiSeverity(sev)}
                      className={`px-3 py-1.5 text-xs font-mono rounded border uppercase transition-colors ${
                        isActive
                          ? colorMap[sev]
                          : "bg-background text-text-muted border-border hover:border-text-muted hover:text-text-secondary"
                      }`}
                    >
                      {sev}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Nuclei rate limit */}
            <div>
              <label className="block text-xs font-mono text-text-muted uppercase tracking-wider mb-2">
                Nuclei Rate Limit:{" "}
                <span className="text-text-primary">{config.nuclei_rate_limit} req/s</span>
              </label>
              <input
                type="range"
                min={10}
                max={500}
                step={10}
                value={config.nuclei_rate_limit || 150}
                onChange={(e) => updateConfig("nuclei_rate_limit", Number(e.target.value))}
                className="w-full h-1.5 bg-background rounded-full appearance-none cursor-pointer accent-accent"
              />
              <div className="flex justify-between text-[10px] font-mono text-text-muted mt-1">
                <span>10 req/s</span>
                <span>500 req/s</span>
              </div>
            </div>

            {/* ZAP toggle */}
            <ToggleField
              label="OWASP ZAP Active Scan"
              description="Run ZAP active spider and scanner against discovered web targets"
              checked={config.enable_zap ?? true}
              onChange={(v) => updateConfig("enable_zap", v)}
            />

            {/* OpenVAS toggle */}
            <ToggleField
              label="OpenVAS Scan"
              description="Run OpenVAS vulnerability scanner (requires Greenbone containers)"
              checked={config.enable_openvas ?? false}
              onChange={(v) => updateConfig("enable_openvas", v)}
              disabled
              disabledReason="OpenVAS containers not available"
            />
          </div>
        </Card>

        {/* Reporting */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-accent" />
              <CardTitle>Reporting</CardTitle>
            </div>
          </CardHeader>
          <ToggleField
            label="Push to DefectDojo"
            description="Automatically create findings in DefectDojo for tracking and remediation"
            checked={config.push_to_defectdojo ?? false}
            onChange={(v) => updateConfig("push_to_defectdojo", v)}
          />
        </Card>

        {/* Error display */}
        {createScan.isError && (
          <div className="bg-severity-critical/10 border border-severity-critical/30 rounded-lg p-4">
            <p className="text-sm font-mono text-severity-critical">
              Failed to create scan. Please check your configuration and try again.
            </p>
          </div>
        )}

        {/* Launch button */}
        <div className="flex justify-center pt-2 pb-8">
          <Button
            type="submit"
            size="lg"
            isLoading={createScan.isPending}
            disabled={createScan.isPending}
            className="px-12 gap-2"
          >
            <Rocket className="h-4 w-4" />
            Launch Scan
          </Button>
        </div>
      </form>
    </div>
  );
}

interface ToggleFieldProps {
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
  disabledReason?: string;
}

function ToggleField({
  label,
  description,
  checked,
  onChange,
  disabled = false,
  disabledReason,
}: ToggleFieldProps) {
  return (
    <div className={`flex items-center justify-between ${disabled ? "opacity-50" : ""}`}>
      <div>
        <p className="text-sm font-mono text-text-primary">{label}</p>
        <p className="text-xs font-mono text-text-muted mt-0.5">{description}</p>
        {disabled && disabledReason && (
          <p className="text-[10px] font-mono text-severity-medium mt-0.5">
            {disabledReason}
          </p>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => !disabled && onChange(!checked)}
        disabled={disabled}
        className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-accent/50 focus:ring-offset-2 focus:ring-offset-background disabled:cursor-not-allowed ${
          checked ? "bg-accent" : "bg-border"
        }`}
      >
        <span
          className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ${
            checked ? "translate-x-5" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}
