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
    extended_questions?: string[];
    code?: string;
    message?: string;
    retryable?: boolean;
    [key: string]: unknown;
  };
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
