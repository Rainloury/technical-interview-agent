import type { HistoryType } from "./types";

export const queryKeys = {
  session: ["session"] as const,
  dashboard: ["dashboard"] as const,
  history: (type: HistoryType) => ["history", type] as const,
  resume: (id: string) => ["resume", id] as const,
};
