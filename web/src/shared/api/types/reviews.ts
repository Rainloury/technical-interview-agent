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

