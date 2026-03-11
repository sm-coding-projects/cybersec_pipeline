import { useEffect, useRef, useState, useCallback } from "react";

export interface WebSocketEvent {
  event: string;
  data: Record<string, unknown>;
  timestamp: number;
}

export interface ScanLiveData {
  target_domain: string | null;
  current_phase: number;
  phase_statuses: Record<number, string>;
  phase_durations: Record<number, number>;
  tool_statuses: Record<string, string>;
  tool_results: Record<string, Record<string, unknown>>;
  subdomains: number;
  ips: number;
  emails: number;
  web_urls: number;
  open_ports: number;
  findings: number;
  logs: Array<{ tool: string; line: string; timestamp: number }>;
  summary: Record<string, unknown> | null;
  error: string | null;
  warnings: string[];
}

const INITIAL_SCAN_DATA: ScanLiveData = {
  target_domain: null,
  current_phase: 0,
  phase_statuses: {},
  phase_durations: {},
  tool_statuses: {},
  tool_results: {},
  subdomains: 0,
  ips: 0,
  emails: 0,
  web_urls: 0,
  open_ports: 0,
  findings: 0,
  logs: [],
  summary: null,
  error: null,
  warnings: [],
};

interface UseWebSocketOptions {
  scanId: number | undefined;
  enabled?: boolean;
  onEvent?: (event: WebSocketEvent) => void;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  lastEvent: WebSocketEvent | null;
  events: WebSocketEvent[];
  scanData: ScanLiveData;
}

const MAX_RECONNECT_DELAY = 30000;
const BASE_RECONNECT_DELAY = 1000;
const MAX_LOG_LINES = 500;

export function useWebSocket({
  scanId,
  enabled = true,
  onEvent,
}: UseWebSocketOptions): UseWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<WebSocketEvent | null>(null);
  const [events, setEvents] = useState<WebSocketEvent[]>([]);
  const [scanData, setScanData] = useState<ScanLiveData>({ ...INITIAL_SCAN_DATA });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shouldReconnectRef = useRef(true);
  const onEventRef = useRef(onEvent);

  // Keep callback ref up to date without triggering reconnects
  onEventRef.current = onEvent;

  const processEvent = useCallback((wsEvent: WebSocketEvent) => {
    setLastEvent(wsEvent);
    setEvents((prev) => [...prev, wsEvent]);
    onEventRef.current?.(wsEvent);

    setScanData((prev) => {
      const next = { ...prev };
      const { event, data } = wsEvent;

      switch (event) {
        case "state_snapshot": {
          // Initial snapshot sent by the server when a WS client connects mid-scan.
          // Restores phase/tool statuses and recent logs so the UI is immediately
          // accurate after a navigation away and back.
          if (typeof data.current_phase === "number" && data.current_phase > 0) {
            next.current_phase = data.current_phase;
          }
          if (data.phase_statuses && typeof data.phase_statuses === "object") {
            const ps = data.phase_statuses as Record<string, string>;
            for (const [k, v] of Object.entries(ps)) {
              next.phase_statuses[parseInt(k, 10)] = v;
            }
          }
          if (data.tool_statuses && typeof data.tool_statuses === "object") {
            next.tool_statuses = {
              ...next.tool_statuses,
              ...(data.tool_statuses as Record<string, string>),
            };
          }
          if (Array.isArray(data.logs)) {
            // Pre-populate log stream; new tool_log events will be appended on top
            next.logs = data.logs as Array<{ tool: string; line: string; timestamp: number }>;
          }
          break;
        }

        case "scan_started":
          next.target_domain = (data.target_domain as string) || null;
          break;

        case "phase_started":
          next.current_phase = data.phase_number as number;
          next.phase_statuses = {
            ...next.phase_statuses,
            [data.phase_number as number]: "running",
          };
          break;

        case "phase_completed":
          next.phase_statuses = {
            ...next.phase_statuses,
            [data.phase_number as number]: "completed",
          };
          if (data.duration_seconds != null) {
            next.phase_durations = {
              ...next.phase_durations,
              [data.phase_number as number]: data.duration_seconds as number,
            };
          }
          break;

        case "phase_failed":
          next.phase_statuses = {
            ...next.phase_statuses,
            [data.phase_number as number]: "failed",
          };
          next.error = (data.error as string) || null;
          break;

        case "tool_started":
          next.tool_statuses = {
            ...next.tool_statuses,
            [data.tool as string]: "running",
          };
          break;

        case "tool_completed":
          next.tool_statuses = {
            ...next.tool_statuses,
            [data.tool as string]: "completed",
          };
          break;

        case "tool_error":
          next.tool_statuses = {
            ...next.tool_statuses,
            [data.tool as string]: "error",
          };
          break;

        case "tool_skipped":
          next.tool_statuses = {
            ...next.tool_statuses,
            [data.tool as string]: "skipped",
          };
          break;

        case "tool_result": {
          const tool = data.tool as string;
          const { tool: _t, ...resultData } = data;
          next.tool_results = {
            ...next.tool_results,
            [tool]: resultData,
          };
          // Accumulate counts from tool results
          if (typeof data.subdomains === "number") {
            next.subdomains += data.subdomains as number;
          }
          if (typeof data.ips === "number") {
            next.ips += data.ips as number;
          }
          if (typeof data.emails === "number") {
            next.emails += data.emails as number;
          }
          if (typeof data.web_urls === "number") {
            next.web_urls += data.web_urls as number;
          }
          if (typeof data.open_ports === "number") {
            next.open_ports += data.open_ports as number;
          }
          break;
        }

        case "tool_log":
          next.logs = [
            ...next.logs.slice(-MAX_LOG_LINES + 1),
            {
              tool: data.tool as string,
              line: data.line as string,
              timestamp: wsEvent.timestamp,
            },
          ];
          break;

        case "finding_discovered":
          next.findings += 1;
          break;

        case "recon_merged":
          if (typeof data.subdomains === "number") next.subdomains = data.subdomains as number;
          if (typeof data.ips === "number") next.ips = data.ips as number;
          if (typeof data.emails === "number") next.emails = data.emails as number;
          break;

        case "pipeline_complete":
          next.summary = data.summary as Record<string, unknown> || data;
          break;

        case "target_unreachable":
          next.warnings = [
            ...next.warnings,
            (data.message as string) || `Target ${data.domain} is unreachable`,
          ];
          // Also add to logs for visibility
          next.logs = [
            ...next.logs.slice(-MAX_LOG_LINES + 1),
            {
              tool: "system",
              line: `WARNING: ${(data.message as string) || "Target unreachable"}`,
              timestamp: wsEvent.timestamp,
            },
          ];
          break;

        case "scan_failed":
          next.error = (data.error as string) || "Scan failed";
          break;
      }

      return next;
    });
  }, []);

  const connect = useCallback(() => {
    if (!scanId || !enabled) return;

    // Determine WebSocket URL from current page location
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/scans/${scanId}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      reconnectAttemptRef.current = 0;
    };

    ws.onmessage = (messageEvent) => {
      try {
        const parsed = JSON.parse(messageEvent.data as string) as {
          event: string;
          data: Record<string, unknown>;
        };
        const wsEvent: WebSocketEvent = {
          event: parsed.event,
          data: parsed.data,
          timestamp: Date.now(),
        };
        processEvent(wsEvent);
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;

      // Reconnect with exponential backoff
      if (shouldReconnectRef.current && enabled) {
        const delay = Math.min(
          BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttemptRef.current),
          MAX_RECONNECT_DELAY
        );
        reconnectAttemptRef.current += 1;
        reconnectTimerRef.current = setTimeout(() => {
          connect();
        }, delay);
      }
    };

    ws.onerror = () => {
      // The onclose handler will fire after this, triggering reconnection
    };
  }, [scanId, enabled, processEvent]);

  useEffect(() => {
    shouldReconnectRef.current = true;

    // Reset state when scanId changes
    setIsConnected(false);
    setLastEvent(null);
    setEvents([]);
    setScanData({ ...INITIAL_SCAN_DATA });
    reconnectAttemptRef.current = 0;

    connect();

    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { isConnected, lastEvent, events, scanData };
}
