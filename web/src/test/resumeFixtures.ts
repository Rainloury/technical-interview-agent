import type {
  ResumeAnalysis,
  ResumeQuestion,
  ResumeState,
  ResumeTask,
} from "../api/types";

const analysis: ResumeAnalysis = {
  schema_version: "1.0",
  skills: {
    items: [
      { name: "Python", level: "advanced", evidence_ids: ["evidence-1"] },
      { name: "PostgreSQL", level: "intermediate", evidence_ids: ["evidence-2"] },
    ],
  },
  projects: {
    items: [
      {
        name: "异步任务平台",
        role: "后端负责人",
        summary: "设计有界 Worker、租约和退避机制。",
        evidence_ids: ["evidence-1"],
      },
    ],
  },
  unverified_items: {
    items: ["团队规模与线上流量尚未核实"],
  },
};

const difficultyMix = [
  "easy",
  "easy",
  "easy",
  "medium",
  "medium",
  "medium",
  "medium",
  "medium",
  "hard",
  "hard",
] as const;

const questions: ResumeQuestion[] = difficultyMix.map((difficulty, index) => ({
  id: `question-${index + 1}`,
  sequence: index + 1,
  question_text: `简历面试问题 ${index + 1}`,
  category: "后端工程",
  difficulty,
  assessment_points: {
    items: [`考察点 ${index + 1}`],
  },
  evidence_refs: {
    ids: index % 2 === 0 ? ["evidence-1"] : ["evidence-2"],
    source_state: "available",
  },
}));

function task(state: ResumeState): ResumeTask {
  return {
    id: "resume-1",
    state,
    failure_stage: null,
    error_code: null,
    analysis: state === "failed" || state === "uploaded" || state === "analyzing"
      ? null
      : analysis,
    questions: state === "completed" || state === "source_deleted" ? questions : [],
    created_at: "2026-10-17T08:00:00Z",
    completed_at: state === "completed" || state === "source_deleted"
      ? "2026-10-17T08:02:00Z"
      : null,
  };
}

export const completedResume = {
  ...task("completed"),
  questions: questions.map((question) => ({
    ...question,
    reference_answer: "敏感参考答案",
    scoring_rubric: { items: ["敏感评分标准"] },
  })),
} as unknown as ResumeTask;

export const analyzingResume = task("analyzing");
export const failedResume: ResumeTask = {
  ...task("failed"),
  failure_stage: "analyze",
  error_code: "provider_timeout",
};
export const sourceDeletedResume = {
  ...task("source_deleted"),
  questions: questions.map((question) => ({
    ...question,
    evidence_refs: {
      ids: question.evidence_refs.items,
      source_state: "source_deleted",
    },
  })),
} as unknown as ResumeTask;
export const resumeQuestions = questions;
