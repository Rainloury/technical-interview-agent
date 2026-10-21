export type HistoryType = "resume" | "qa" | "interview" | "wrong_question";

export interface UserSummary {
  id: string;
  display_name: string | null;
}

export interface SessionSummary {
  expires_at: string;
}

export interface Session {
  user: UserSummary;
  session: SessionSummary;
}

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

export type QaState = "created" | "retrieving" | "answering" | "completed" | "failed";
export type QaAnswerPreference = "concise" | "detailed";
export type QaEvidenceStatus = "supported" | "model_knowledge" | "insufficient";
export type QaEvidenceSourceKind = "system" | "user_document";

export interface QaAccepted {
  qa_request_id: string;
  stream_url: string;
  state: QaState;
}

export interface QaAnswer {
  direct_answer: string;
  explanation: string;
  evidence_ids: string[];
  extended_questions: string[];
  evidence_status: QaEvidenceStatus;
}

export interface QaEvidence {
  citation_id: string;
  title: string;
  section_path: string;
  snippet: string;
  relevance_score: number;
  source_state: "available" | "source_deleted";
  source_kind: QaEvidenceSourceKind;
}

export interface QaRequest {
  id: string;
  question: string;
  answer_preference: QaAnswerPreference;
  state: QaState;
  answer: QaAnswer | null;
  evidence: QaEvidence[];
  evidence_status: QaEvidenceStatus;
  error: {
    code?: string;
    message?: string;
    retryable?: boolean;
  } | null;
  created_at: string;
  completed_at: string | null;
  last_event_seq: number;
}

export interface QaStreamEvent {
  id: number;
  type: "started" | "delta" | "evidence" | "completed" | "error";
  data: {
    text?: string;
    answer?: QaAnswer;
    evidence?: QaEvidence[];
    source_kind?: QaEvidenceSourceKind;
    vector_status?: "ok" | "degraded" | "disabled";
    extended_questions?: string[];
    code?: string;
    message?: string;
    retryable?: boolean;
    [key: string]: unknown;
  };
}

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

export interface WrongQuestion {
  id: string;
  turn_id: string;
  parent_turn_id: string | null;
  question_text: string;
  topic_key: string;
  difficulty: "easy" | "medium" | "hard";
  score_breakdown: Record<string, unknown>;
  loss_reasons: string[];
  created_at: string;
}

export interface WrongQuestionDetail extends WrongQuestion {
  interview_id: string;
  answer_text: string;
  reference_answer: string;
  state: string;
  expires_at: string;
}

export interface WeakPointEvidence {
  wrong_question_id: string;
  turn_id: string;
  loss_reason_hash: string;
}

export interface WeakPoint {
  id: string;
  topic_key: string;
  title: string;
  severity: number;
  failure_count: number;
  last_failure_at: string;
  review_advice: Record<string, unknown>;
  state: string;
  evidence: WeakPointEvidence[];
}

export interface ReviewPage<T> {
  items: T[];
  next_cursor: string | null;
}

export type DataDeletionState =
  | "requested"
  | "deleting"
  | "completed"
  | "failed";

export interface DataDeletionAccepted {
  request_id: string;
  state: "requested";
  accepted_at: string;
}

export interface DataDeletionStatus {
  request_id: string;
  state: DataDeletionState;
  scope: string[];
  result: Record<string, unknown> | null;
  error_code: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export type ResumeState =
  | "uploaded"
  | "extracting"
  | "analyzing"
  | "generating_questions"
  | "completed"
  | "failed"
  | "source_deleted";

export type ResumeFailureStage = "upload" | "extract" | "analyze" | "generate";

export interface ResumeAccepted {
  resume_task_id: string;
  state: ResumeState;
  created_at: string;
}

export interface ResumeAnalysisSection {
  items?: unknown[];
  [key: string]: unknown;
}

export interface ResumeAnalysis {
  schema_version: string;
  skills: ResumeAnalysisSection;
  projects: ResumeAnalysisSection;
  unverified_items: ResumeAnalysisSection;
}

export interface ResumeQuestion {
  id: string;
  sequence: number;
  question_text: string;
  category: string;
  difficulty: "easy" | "medium" | "hard";
  assessment_points: ResumeAnalysisSection;
  evidence_refs: ResumeAnalysisSection;
}

export interface ResumeTask {
  id: string;
  state: ResumeState;
  failure_stage: ResumeFailureStage | null;
  error_code: string | null;
  analysis: ResumeAnalysis | null;
  questions: ResumeQuestion[];
  created_at: string;
  completed_at: string | null;
}

export interface LoginResponse {
  user: UserSummary;
  session: SessionSummary;
}

export interface RegisterResponse {
  accepted: true;
  next_action: "login";
}

export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    retryable?: boolean;
    request_id?: string;
  };
}
