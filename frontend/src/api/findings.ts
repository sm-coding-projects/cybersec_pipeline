import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "./client";
import type { Finding, FindingUpdate } from "@/types/finding";
import type { PaginatedResponse } from "@/types/api";

interface FindingsParams {
  page?: number;
  perPage?: number;
  severity?: string;
  sourceTool?: string;
  status?: string;
  search?: string;
  sortBy?: string;
  sortOrder?: "asc" | "desc";
  scanId?: number;
}

export function useFindings(params: FindingsParams = {}) {
  const {
    page = 1,
    perPage = 20,
    severity,
    sourceTool,
    status,
    search,
    sortBy,
    sortOrder,
    scanId,
  } = params;

  return useQuery({
    queryKey: ["findings", params],
    queryFn: async () => {
      const url = scanId ? `/scans/${scanId}/findings` : "/findings";
      const { data } = await apiClient.get<PaginatedResponse<Finding>>(url, {
        params: {
          page,
          per_page: perPage,
          severity,
          source_tool: sourceTool,
          status,
          search,
          sort_by: sortBy,
          sort_order: sortOrder,
        },
      });
      return data;
    },
  });
}

export function useFinding(findingId: number | undefined) {
  return useQuery({
    queryKey: ["finding", findingId],
    queryFn: async () => {
      const { data } = await apiClient.get<Finding>(`/findings/${findingId}`);
      return data;
    },
    enabled: !!findingId,
  });
}

export function useUpdateFinding() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      findingId,
      update,
    }: {
      findingId: number;
      update: FindingUpdate;
    }) => {
      const { data } = await apiClient.patch<Finding>(
        `/findings/${findingId}`,
        update
      );
      return data;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["finding", variables.findingId],
      });
      queryClient.invalidateQueries({ queryKey: ["findings"] });
    },
  });
}
