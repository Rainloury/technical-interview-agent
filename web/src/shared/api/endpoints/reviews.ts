import { request } from "@/shared/api/http";
import type { ReviewPage, WeakPoint, WrongQuestionDetail } from "@/shared/api/types";

export const reviewsEndpoints = {
  wrongQuestions: (cursor?: string | null, limit = 20) =>
    request<ReviewPage<WrongQuestionDetail>>("/api/v1/wrong-questions", {
      query: { cursor, limit },
    }),
  wrongQuestion: (id: string) =>
    request<WrongQuestionDetail>(`/api/v1/wrong-questions/${id}`),
  weakPoints: (cursor?: string | null, limit = 20) =>
    request<ReviewPage<WeakPoint>>("/api/v1/weak-points", {
      query: { cursor, limit },
    }),
};
