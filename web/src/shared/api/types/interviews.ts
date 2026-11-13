import type { WeakPoint, WrongQuestion } from "@/shared/api/types/reviews";

export type InterviewDirection = "backend" | "frontend" | "fullstack";
export type InterviewDifficulty = "foundation" | "balanced" | "challenge";
export type InterviewState =
  | "created"
  | "in_progress"
  | "completed"
  | "cancelled"
  | "timed_out"
  | "failed";
export type InterviewTurnState =
  | "pending"
  | "awaiting_answer"
  | "scoring"
  | "passed"
  | "failed"
  | "scoring_failed"
  | "branch_completed"
  | "skipped"
  | "unanswered"
  | "cancelled";
export type InterviewTurnType = "main" | "follow_up";

export interface InterviewConfiguration {
  direction: InterviewDirection;
  difficulty: InterviewDifficulty;
  topic_keys: string[];
}

export interface InterviewCreated {
  interview_id: string;
  state: InterviewState;
  main_question_count: number;
  deadline_at: string | null;
  configuration: InterviewConfiguration;
}

export interface InterviewTurn {
  id: string;
  type: InterviewTurnType;
  depth: number;
  question_text: string;
  topic_key: string;
  difficulty: "easy" | "medium" | "hard";
  state: InterviewTurnState;
}

export interface InterviewProgress {
  main_questions_completed: number;
  main_questions_total: number;
  main_questions_remaining: number;
  current_follow_up_chain:
    | "awaiting_answer"
    | "scoring"
    | "generating_follow_up"
    | "completed"
    | null;
  remaining_seconds: number;
}

export interface InterviewStart {
  interview_id: string;
  state: InterviewState;
  server_time: string;
  deadline_at: string | null;
  current_turn: InterviewTurn | null;
  progress: InterviewProgress;
}

export interface Interview {
  interview_id: string;
  state: InterviewState;
  direction: InterviewDirection;
  configuration: InterviewConfiguration;
  server_time: string;
  deadline_at: string | null;
  ended_at: string | null;
  current_turn: InterviewTurn | null;
  submitted_turns: InterviewTurn[];
  progress: InterviewProgress;
}

export interface InterviewAccepted {
  turn_id: string;
  state: "scoring";
  accepted_at: string;
  progress: InterviewProgress;
  next_action: "wait";
}

export interface InterviewBranchAction {
  interview_id: string;
  turn_id: string;
  state: InterviewState;
  progress: InterviewProgress;
  next_action: "wait";
}

export interface InterviewReportTurn {
  id: string;
  parent_turn_id: string | null;
  type: InterviewTurnType;
  depth: number;
  question_text: string;
  topic_key: string;
  difficulty: "easy" | "medium" | "hard";
  result: InterviewTurnState;
  score_total: number | null;
  score_band: "below_70" | "70_84" | "85_plus" | null;
  score_breakdown: Record<string, unknown> | null;
  loss_reasons: string[];
  reference_answer: string | null;
  submitted_at: string | null;
}

export interface InterviewReport {
  interview_id: string;
  state: InterviewState;
  direction: InterviewDirection;
  scoring_status: "complete" | "incomplete_scoring";
  server_time: string;
  summary: {
    main_question_count: number;
    follow_up_count: number;
    passed_count: number;
    failed_count: number;
    skipped_count?: number;
    unanswered_count?: number;
    scoring_failed_count?: number;
  };
  turns: InterviewReportTurn[];
  wrong_questions: WrongQuestion[];
  weak_points: WeakPoint[];
}

