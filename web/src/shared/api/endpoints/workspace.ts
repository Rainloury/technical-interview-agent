import { request } from "@/shared/api/http";
import type { Dashboard, HistoryPage, HistoryType } from "@/shared/api/types";

export const workspaceEndpoints = {
  dashboard: () => request<Dashboard>("/api/v1/dashboard"),
  history: (type: HistoryType, cursor?: string | null, limit = 10) =>
    request<HistoryPage>("/api/v1/history", {
      query: { type, limit, cursor },
    }),
};
