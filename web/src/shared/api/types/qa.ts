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

