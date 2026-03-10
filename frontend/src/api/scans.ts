import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "./client";
import type { Scan, ScanCreate } from "@/types/scan";
import type { PaginatedResponse } from "@/types/api";

export function useScans(page = 1, perPage = 20) {
  return useQuery({
    queryKey: ["scans", page, perPage],
    queryFn: async () => {
      const { data } = await apiClient.get<PaginatedResponse<Scan>>("/scans", {
        params: { page, per_page: perPage },
      });
      return data;
    },
  });
}

export function useScan(scanId: number | undefined) {
  return useQuery({
    queryKey: ["scan", scanId],
    queryFn: async () => {
      const { data } = await apiClient.get<Scan>(`/scans/${scanId}`);
      return data;
    },
    enabled: !!scanId,
    refetchInterval: (query) => {
      const scan = query.state.data;
      // Auto-refresh running scans every 3 seconds
      if (scan && (scan.status === "running" || scan.status === "pending")) {
        return 3000;
      }
      return false;
    },
  });
}

export function useCreateScan() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (scanData: ScanCreate) => {
      const { data } = await apiClient.post<Scan>("/scans", scanData);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scans"] });
    },
  });
}

export function useDeleteScan() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (scanId: number) => {
      await apiClient.delete(`/scans/${scanId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scans"] });
    },
  });
}
