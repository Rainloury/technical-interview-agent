import { request } from "@/shared/api/http";
import type { Interview, InterviewAccepted, InterviewBranchAction, InterviewCreated, InterviewDifficulty, InterviewDirection, InterviewReport, InterviewStart } from "@/shared/api/types";

export const interviewsEndpoints = {
  createInterview: (
    direction: InterviewDirection,
    difficulty: InterviewDifficulty,
    topicKeys: string[],
    idempotencyKey: string,
  ) =>
    request<InterviewCreated>("/api/v1/interviews", {
      method: "POST",
      body: { direction, difficulty, topic_keys: topicKeys },
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  startInterview: (id: string, idempotencyKey: string) =>
    request<InterviewStart>(`/api/v1/interviews/${id}/start`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  interview: (id: string) => request<Interview>(`/api/v1/interviews/${id}`),
  answerInterview: (
    id: string,
    turnId: string,
    answer: string,
    idempotencyKey: string,
  ) =>
    request<InterviewAccepted>(
      `/api/v1/interviews/${id}/turns/${turnId}/answer`,
      {
        method: "POST",
        body: {
          answer,
          client_submitted_at: new Date().toISOString(),
        },
        headers: { "Idempotency-Key": idempotencyKey },
      },
    ),
  skipInterviewTurn: (id: string, turnId: string, key: string) =>
    request<InterviewBranchAction>(
      `/api/v1/interviews/${id}/turns/${turnId}/skip`,
      { method: "POST", headers: { "Idempotency-Key": key } },
    ),
  endInterviewBranch: (id: string, turnId: string, key: string) =>
    request<InterviewBranchAction>(
      `/api/v1/interviews/${id}/turns/${turnId}/end-branch`,
      { method: "POST", headers: { "Idempotency-Key": key } },
    ),
  interviewReport: (id: string) =>
    request<InterviewReport>(`/api/v1/interviews/${id}/report`),
};
