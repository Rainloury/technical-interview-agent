import { http, HttpResponse } from "msw";

import { api, ApiError } from "./client";
import { server } from "../test/server";

describe("api client", () => {
  it("sends credentials and the explicit CSRF header for writes", async () => {
    let receivedCsrf: string | null = null;
    server.use(
      http.post("*/api/v1/auth/logout", ({ request }) => {
        receivedCsrf = request.headers.get("X-CSRF-Token");
        return new HttpResponse(null, { status: 204 });
      }),
    );
    document.cookie = "interview_csrf=csrf-from-cookie; path=/";

    await api.logout();

    expect(receivedCsrf).toBe("csrf-from-cookie");
  });

  it("maps the stable error envelope into ApiError", async () => {
    server.use(
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json(
          {
            error: {
              code: "invalid_credentials",
              message: "邮箱或密码不正确",
              retryable: false,
              request_id: "req-test",
            },
          },
          { status: 401 },
        ),
      ),
    );

    await expect(api.login("user@example.com", "password")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      code: "invalid_credentials",
      requestId: "req-test",
    } satisfies Partial<ApiError>);
  });

  it("uploads multipart data with CSRF and idempotency without a JSON content type", async () => {
    let contentType: string | null = null;
    let csrf: string | null = null;
    let idempotencyKey: string | null = null;
    server.use(
      http.post("*/api/v1/resumes", ({ request }) => {
        contentType = request.headers.get("Content-Type");
        csrf = request.headers.get("X-CSRF-Token");
        idempotencyKey = request.headers.get("Idempotency-Key");
        return HttpResponse.json({
          resume_task_id: "resume-1",
          state: "uploaded",
          created_at: "2026-10-17T08:00:00Z",
        }, {
          status: 202,
        });
      }),
    );
    document.cookie = "interview_csrf=csrf-upload; path=/";
    const file = new File(["resume"], "backend.pdf", {
      type: "application/pdf",
    });

    await api.uploadResume(file, " 高级后端工程师 ", "upload-key-1");

    expect(contentType).toMatch(/^multipart\/form-data; boundary=/);
    expect(contentType).not.toContain("application/json");
    expect(csrf).toBe("csrf-upload");
    expect(idempotencyKey).toBe("upload-key-1");
  });

  it("sends idempotency keys for retry and returns undefined for a 204 delete", async () => {
    let retryKey: string | null = null;
    let deleteKey: string | null = null;
    server.use(
      http.post("*/api/v1/resumes/resume-1/retry", ({ request }) => {
        retryKey = request.headers.get("Idempotency-Key");
        return HttpResponse.json(
          {
            resume_task_id: "resume-2",
            state: "uploaded",
            created_at: "2026-10-17T08:00:00Z",
          },
          { status: 202 },
        );
      }),
      http.delete("*/api/v1/resumes/resume-1/source", ({ request }) => {
        deleteKey = request.headers.get("Idempotency-Key");
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await api.retryResume("resume-1", "retry-key-1");
    const deleted = await api.deleteResumeSource("resume-1", "delete-key-1");

    expect(retryKey).toBe("retry-key-1");
    expect(deleteKey).toBe("delete-key-1");
    expect(deleted).toBeUndefined();
  });
});
