import { useQuery } from "@tanstack/react-query";
import apiClient from "./client";
import type {
  DashboardStats,
  SeverityBreakdown,
  ScanTimelineEntry,
} from "@/types/finding";

export function useDashboardStats() {
  return useQuery({
    queryKey: ["dashboard", "stats"],
    queryFn: async () => {
      const { data } = await apiClient.get<DashboardStats>("/dashboard/stats");
      return data;
    },
    refetchInterval: 30000, // Refresh every 30 seconds
  });
}

export function useSeverityBreakdown() {
  return useQuery({
    queryKey: ["dashboard", "severity-breakdown"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ items: SeverityBreakdown[] }>(
        "/dashboard/severity-breakdown"
      );
      return data.items;
    },
    refetchInterval: 30000,
  });
}

export function useScanTimeline() {
  return useQuery({
    queryKey: ["dashboard", "scan-timeline"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ items: ScanTimelineEntry[] }>(
        "/dashboard/scan-timeline"
      );
      return data.items;
    },
    refetchInterval: 30000,
  });
}
