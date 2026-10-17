import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { validateFile } from "./ResumeUploadPage";
import { authenticatedSessionHandler, server } from "../test/server";
import { renderApp } from "../test/render";

const PDF = "application/pdf";

function file(name: string, content = "resume", size?: number): File {
  return size === undefined
    ? new File([content], name, { type: PDF })
    : new File([new Uint8Array(size)], name, { type: PDF });
}

function uploadHandler(onUpload: (request: Request) => void) {
  return http.post("*/api/v1/resumes", ({ request }) => {
    onUpload(request);
    return HttpResponse.json(
      {
        resume_task_id: "resume-accepted-1",
        state: "uploaded",
        created_at: "2026-10-17T08:00:00Z",
      },
      { status: 202 },
    );
  });
}

describe("ResumeUploadPage", () => {
  it("uploads a resume with CSRF and a stable idempotency key", async () => {
    const user = userEvent.setup();
    const observed: {
      csrf: string | null;
      key: string | null;
      contentType: string | null;
    }[] = [];
    server.use(
      authenticatedSessionHandler(),
      uploadHandler((request) => {
        observed.push({
          csrf: request.headers.get("X-CSRF-Token"),
          key: request.headers.get("Idempotency-Key"),
          contentType: request.headers.get("Content-Type"),
        });
      }),
    );
    document.cookie = "interview_csrf=upload-csrf; path=/";
    renderApp("/resumes/new");

    await user.upload(
      await screen.findByLabelText("简历文件"),
      file("backend.pdf"),
    );
    await user.click(screen.getByRole("button", { name: "开始分析" }));

    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/resumes/resume-accepted-1",
      );
    });
    expect(observed).toHaveLength(1);
    expect(observed[0]?.csrf).toBe("upload-csrf");
    expect(observed[0]?.key).toBeTruthy();
    expect(observed[0]?.contentType).toMatch(/^multipart\/form-data; boundary=/);
  });

  it("reuses the idempotency key when retrying the same unchanged file", async () => {
    const user = userEvent.setup();
    const keys: string[] = [];
    let attempts = 0;
    server.use(
      authenticatedSessionHandler(),
      http.post("*/api/v1/resumes", ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key") ?? "");
        attempts += 1;
        if (attempts === 1) {
          return HttpResponse.json(
            {
              error: {
                code: "provider_unavailable",
                message: "上传暂时失败",
                retryable: true,
              },
            },
            { status: 503 },
          );
        }
        return HttpResponse.json(
          {
            resume_task_id: "resume-accepted-2",
            state: "uploaded",
            created_at: "2026-10-17T08:00:00Z",
          },
          { status: 202 },
        );
      }),
    );
    renderApp("/resumes/new");

    await user.upload(
      await screen.findByLabelText("简历文件"),
      file("retry.pdf"),
    );
    await user.click(screen.getByRole("button", { name: "开始分析" }));
    expect(await screen.findByText("上传暂时失败")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试" }));

    await waitFor(() => expect(keys).toHaveLength(2));
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
  });

  it("rejects unsupported extensions and oversized files before a request", async () => {
    const user = userEvent.setup();
    let requests = 0;
    server.use(
      authenticatedSessionHandler(),
      http.post("*/api/v1/resumes", () => {
        requests += 1;
        return HttpResponse.json({}, { status: 202 });
      }),
    );
    renderApp("/resumes/new");
    const input = (await screen.findByLabelText("简历文件")) as HTMLInputElement;

    await user.upload(input, file("resume.exe", "binary"));
    expect(await screen.findByText("仅支持 PDF 或 DOCX 文件。")).toBeInTheDocument();
    expect(validateFile(input.files?.[0] ?? null)).toBe("仅支持 PDF 或 DOCX 文件。");

    await user.upload(input, file("large.pdf", "x", 10 * 1024 * 1024 + 1));
    expect(await screen.findByText("文件不能超过 10 MB。")).toBeInTheDocument();
    expect(validateFile(input.files?.[0] ?? null)).toBe("文件不能超过 10 MB。");
    expect(requests).toBe(0);
  });
});
