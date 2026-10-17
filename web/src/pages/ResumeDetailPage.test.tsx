import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import {
  analyzingResume,
  completedResume,
  failedResume,
  sourceDeletedResume,
} from "../test/resumeFixtures";
import { authenticatedSessionHandler, server } from "../test/server";
import { renderApp } from "../test/render";

describe("ResumeDetailPage", () => {
  it("polls an analyzing task until completion and then stops", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let requests = 0;
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/resumes/resume-1", () => {
        requests += 1;
        return HttpResponse.json(requests === 1 ? analyzingResume : completedResume);
      }),
    );
    renderApp("/resumes/resume-1");

    expect(await screen.findByText("正在处理简历")).toBeInTheDocument();
    await vi.advanceTimersByTimeAsync(1500);
    expect(await screen.findByText("简历面试问题 10")).toBeInTheDocument();
    expect(document.querySelectorAll(".question-card")).toHaveLength(10);
    const settledRequests = requests;
    await vi.advanceTimersByTimeAsync(1500);
    expect(requests).toBe(settledRequests);
    vi.useRealTimers();
  });

  it("renders the analysis and 10 questions without leaking protected fields", async () => {
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/resumes/resume-1", () =>
        HttpResponse.json(completedResume),
      ),
    );
    const { container } = renderApp("/resumes/resume-1");

    expect(await screen.findByText("结构化分析")).toBeInTheDocument();
    expect(screen.getByText("异步任务平台")).toBeInTheDocument();
    expect(screen.getByText("10 道")).toBeInTheDocument();
    expect(container.textContent).not.toContain("敏感参考答案");
    expect(container.textContent).not.toContain("敏感评分标准");
  });

  it("retries a failed task and navigates to the accepted task", async () => {
    const user = userEvent.setup();
    let retryKey: string | null = null;
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/resumes/resume-1", () => HttpResponse.json(failedResume)),
      http.post("*/api/v1/resumes/resume-1/retry", ({ request }) => {
        retryKey = request.headers.get("Idempotency-Key");
        return HttpResponse.json(
          {
            resume_task_id: "resume-retried-1",
            state: "uploaded",
            created_at: "2026-10-17T08:03:00Z",
          },
          { status: 202 },
        );
      }),
    );
    document.cookie = "interview_csrf=retry-csrf; path=/";
    renderApp("/resumes/resume-1");

    expect(
      await screen.findByRole("heading", { name: "简历处理未完成" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重新处理" }));
    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/resumes/resume-retried-1",
      );
    });
    expect(retryKey).toBeTruthy();
  });

  it("requires confirmation before deleting a source and handles a 204 response", async () => {
    const user = userEvent.setup();
    let deleteKey: string | null = null;
    let deleted = false;
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/resumes/resume-1", () =>
        HttpResponse.json(deleted ? sourceDeletedResume : completedResume),
      ),
      http.delete("*/api/v1/resumes/resume-1/source", ({ request }) => {
        deleteKey = request.headers.get("Idempotency-Key");
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderApp("/resumes/resume-1");

    await user.click(
      await screen.findByRole("button", { name: "删除原始简历" }),
    );
    expect(deleteKey).toBeNull();
    expect(screen.getByText("此操作不可撤销。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认删除" }));

    expect(await screen.findByText("原始简历已删除")).toBeInTheDocument();
    expect(deleteKey).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "删除原始简历" }),
    ).not.toBeInTheDocument();
  });
});
