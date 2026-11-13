import { request } from "@/shared/api/http";
import { streamQa } from "@/shared/api/sse";
import type { QaAccepted, QaAnswerPreference, QaRequest } from "@/shared/api/types";

export const qaEndpoints = {
  createQa: (
    question: string,
    answerPreference: QaAnswerPreference,
    idempotencyKey: string,
  ) =>
    request<QaAccepted>("/api/v1/qa", {
      method: "POST",
      body: {
        question,
        answer_preference: answerPreference,
      },
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  qa: (id: string) => request<QaRequest>(`/api/v1/qa/${id}`),
  streamQa,
};
