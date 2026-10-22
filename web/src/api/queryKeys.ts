import type { HistoryType } from "./types";

export const queryKeys = {
  session: ["session"] as const,
  dashboard: ["dashboard"] as const,
  history: (type: HistoryType) => ["history", type] as const,
  documents: ["documents"] as const,
  document: (id: string) => ["documents", id] as const,
  resume: (id: string) => ["resume", id] as const,
  qa: (id: string) => ["qa", id] as const,
  interview: (id: string) => ["interview", id] as const,
  interviewReport: (id: string) => ["interview", id, "report"] as const,
  wrongQuestions: ["wrong-questions"] as const,
  weakPoints: ["weak-points"] as const,
};
