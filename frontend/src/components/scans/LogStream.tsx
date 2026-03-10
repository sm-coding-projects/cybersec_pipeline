import { useEffect, useRef, useState } from "react";
import { Pin, PinOff } from "lucide-react";
import { TOOL_NAMES } from "@/utils/constants";

interface LogEntry {
  tool: string;
  line: string;
  timestamp: number;
}

interface LogStreamProps {
  logs: LogEntry[];
  className?: string;
}

function formatTimestamp(ts: number): string {
  const date = new Date(ts);
  return date.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function getToolColor(tool: string): string {
  const colors: Record<string, string> = {
    theharvester: "text-cyan-400",
    amass: "text-blue-400",
    dnsx: "text-indigo-400",
    masscan: "text-orange-400",
    nmap: "text-yellow-400",
    "nmap-scanner": "text-yellow-400",
    httpx: "text-green-400",
    nuclei: "text-purple-400",
    zap: "text-red-400",
    openvas: "text-rose-400",
    defectdojo: "text-emerald-400",
  };
  return colors[tool] || "text-text-secondary";
}

export default function LogStream({ logs, className = "" }: LogStreamProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pinToBottom, setPinToBottom] = useState(true);
  const [filterTool, setFilterTool] = useState<string | null>(null);

  // Auto-scroll to bottom when pinned
  useEffect(() => {
    if (pinToBottom && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, pinToBottom]);

  // Detect manual scroll to unpin
  function handleScroll() {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 30;
    if (!isAtBottom && pinToBottom) {
      setPinToBottom(false);
    } else if (isAtBottom && !pinToBottom) {
      setPinToBottom(true);
    }
  }

  // Get unique tools from logs for filter
  const toolsInLogs = Array.from(new Set(logs.map((l) => l.tool)));

  const filteredLogs = filterTool
    ? logs.filter((l) => l.tool === filterTool)
    : logs;

  return (
    <div className={`flex flex-col bg-[#0a0e17] rounded-lg border border-border overflow-hidden ${className}`}>
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-2 bg-surface border-b border-border">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono font-bold text-text-muted uppercase tracking-widest">
            Live Log
          </span>
          <span className="text-[10px] font-mono text-text-muted">
            ({filteredLogs.length} lines)
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Tool filter */}
          {toolsInLogs.length > 1 && (
            <select
              value={filterTool || ""}
              onChange={(e) => setFilterTool(e.target.value || null)}
              className="bg-background border border-border rounded px-2 py-0.5 text-[10px] font-mono text-text-secondary focus:outline-none focus:border-accent"
            >
              <option value="">All tools</option>
              {toolsInLogs.map((t) => (
                <option key={t} value={t}>
                  {TOOL_NAMES[t] || t}
                </option>
              ))}
            </select>
          )}

          {/* Pin toggle */}
          <button
            onClick={() => {
              setPinToBottom(!pinToBottom);
              if (!pinToBottom && containerRef.current) {
                containerRef.current.scrollTop = containerRef.current.scrollHeight;
              }
            }}
            className={`p-1 rounded transition-colors ${
              pinToBottom
                ? "text-accent hover:bg-accent/10"
                : "text-text-muted hover:bg-surface-elevated"
            }`}
            title={pinToBottom ? "Unpin from bottom" : "Pin to bottom"}
          >
            {pinToBottom ? (
              <Pin className="h-3.5 w-3.5" />
            ) : (
              <PinOff className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Log content */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-3 min-h-[200px] max-h-[400px] font-mono text-xs leading-5"
      >
        {filteredLogs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-text-muted text-xs font-mono">
            Waiting for log output...
          </div>
        ) : (
          filteredLogs.map((entry, index) => (
            <div
              key={index}
              className="flex gap-2 hover:bg-white/[0.02] transition-colors"
            >
              <span className="text-text-muted flex-shrink-0 select-none">
                {formatTimestamp(entry.timestamp)}
              </span>
              <span
                className={`flex-shrink-0 min-w-[90px] ${getToolColor(entry.tool)}`}
              >
                [{TOOL_NAMES[entry.tool] || entry.tool}]
              </span>
              <span className="text-text-secondary whitespace-pre-wrap break-all">
                {entry.line}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
