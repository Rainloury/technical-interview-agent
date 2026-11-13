import type { UserSummary } from "@/shared/api/types/auth";

export type HistoryType = "resume" | "qa" | "interview" | "wrong_question";

export interface RecentTask {
  id: string;
  type: "resume" | "qa";
  title: string;
  state: string;
  updated_at: string;
}

export interface RecentInterview {
  id: string;
  direction: "backend" | "frontend" | "fullstack";
  state: string;
  updated_at: string;
}

export interface Dashboard {
  user: UserSummary;
  recent_tasks: RecentTask[];
  recent_interviews: RecentInterview[];
  server_time: string;
}

export interface HistoryItem {
  id: string;
  type: HistoryType;
  title: string;
  state: string;
  updated_at: string;
}

export interface HistoryPage {
  items: HistoryItem[];
  next_cursor: string | null;
}

