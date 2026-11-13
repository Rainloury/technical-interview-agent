import { request } from "@/shared/api/http";
import type { ResumeAccepted, ResumeTask } from "@/shared/api/types";

export const resumesEndpoints = {
  resume: (id: string) => request<ResumeTask>(`/api/v1/resumes/${id}`),
  uploadResume: (
    file: File,
    targetRole: string,
    idempotencyKey: string,
  ) => {
    const formData = new FormData();
    formData.set("file", file);
    if (targetRole.trim()) {
      formData.set("target_role", targetRole.trim());
    }
    return request<ResumeAccepted>("/api/v1/resumes", {
      method: "POST",
      formData,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
  retryResume: (id: string, idempotencyKey: string) =>
    request<ResumeAccepted>(`/api/v1/resumes/${id}/retry`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  deleteResumeSource: (id: string, idempotencyKey: string) =>
    request<void>(`/api/v1/resumes/${id}/source`, {
      method: "DELETE",
      headers: { "Idempotency-Key": idempotencyKey },
    }),
};
