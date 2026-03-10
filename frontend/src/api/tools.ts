import { useQuery } from "@tanstack/react-query";
import apiClient from "./client";
import type { ToolStatusResponse } from "@/types/api";

export function useToolStatus() {
  return useQuery({
    queryKey: ["tools", "status"],
    queryFn: async () => {
      const { data } =
        await apiClient.get<ToolStatusResponse>("/tools/status");
      return data;
    },
    refetchInterval: 30000, // Poll every 30 seconds
  });
}
