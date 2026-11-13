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

