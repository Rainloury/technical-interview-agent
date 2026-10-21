import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";

import { api } from "../api/client";
import type { QaAnswer, QaEvidence, QaRequest } from "../api/types";
import { authenticatedSessionHandler, server } from "../test/server";
import { renderApp } from "../test/render";

describe("QaPage", () => {
  it("validates empty, oversized, and URL-like questions without sending a request", async () => {
    const user = userEvent.setup();
    let requests = 0;
    server.use(
      authenticatedSessionHandler(),
      http.post("*/api/v1/qa", () => {
        requests += 1;
        return HttpResponse.json({}, { status: 500 });
      }),
    );
    renderApp("/qa");

    const submit = await screen.findByRole("button", { name: "开始检索" });
    expect(submit).toBeDisabled();
    await user.click(submit);
    expect(requests).toBe(0);

    const question = screen.getByLabelText("技术问题");
    await user.type(question, "https://example.com/interview");
    await user.click(submit);
    expect(
      await screen.findByText("问题中不能包含 URL，检索只使用已审核知识源。"),
    ).toBeInTheDocument();
    expect(requests).toBe(0);

    fireEvent.change(question, { target: { value: "a".repeat(2001) } });
    expect(question).toHaveValue("a".repeat(2000));
    expect(requests).toBe(0);
  });

  it("creates a question with CSRF and a stable idempotency key, then opens detail", async () => {
    const user = userEvent.setup();
    let body: unknown = null;
    let idempotencyKey: string | null = null;
    let csrfToken: string | null = null;
    server.use(
      authenticatedSessionHandler(),
      http.post("*/api/v1/qa", async ({ request }) => {
        body = await request.json();
        idempotencyKey = request.headers.get("Idempotency-Key");
        csrfToken = request.headers.get("X-CSRF-Token");
        return HttpResponse.json(
          {
            qa_request_id: "qa-created-1",
            stream_url: "/api/v1/qa/qa-created-1/stream",
            state: "created",
          },
          { status: 202 },
        );
      }),
    );
    document.cookie = "interview_csrf=qa-csrf; path=/";
    renderApp("/qa");

    await user.type(
      await screen.findByLabelText("技术问题"),
      "如何设计有界重试？",
    );
    await user.click(screen.getByLabelText(/详细回答/));
    await user.click(screen.getByRole("button", { name: "开始检索" }));

    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/qa/qa-created-1",
      );
    });
    expect(body).toEqual({
      question: "如何设计有界重试？",
      answer_preference: "detailed",
    });
    expect(csrfToken).toBe("qa-csrf");
    expect(idempotencyKey).toBeTruthy();
  });

  it("prefills the question when a follow-up is opened from a QA answer", async () => {
    const followUp = "存储过程和函数（Function）有什么区别？";
    const evidence: QaEvidence = {
      citation_id: "evidence-1",
      title: "存储过程与函数",
      section_path: "数据库 / 存储过程",
      snippet: "函数通常返回值，存储过程可以包含更完整的业务步骤。",
      relevance_score: 0.9,
      source_state: "available",
    };
    const answer: QaAnswer = {
      direct_answer: "两者在返回值、调用方式和适用场景上不同。",
      explanation: "函数通常用于计算并返回值，存储过程更适合组织多条语句。",
      evidence_ids: ["evidence-1"],
      extended_questions: [followUp],
      evidence_status: "supported",
    };
    const completedRequest: QaRequest = {
      id: "qa-1",
      question: "存储过程是什么？",
      answer_preference: "concise",
      state: "completed",
      answer,
      evidence: [evidence],
      evidence_status: "supported",
      error: null,
      created_at: "2026-10-20T08:00:00Z",
      completed_at: "2026-10-20T08:00:05Z",
      last_event_seq: 4,
    };
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/qa/qa-1", () => HttpResponse.json(completedRequest)),
    );
    vi.spyOn(api, "streamQa");

    const user = userEvent.setup();
    renderApp("/qa/qa-1");

    await user.click(
      await screen.findByRole("link", { name: followUp }),
    );

    expect(await screen.findByLabelText("技术问题")).toHaveValue(followUp);
  });
});
