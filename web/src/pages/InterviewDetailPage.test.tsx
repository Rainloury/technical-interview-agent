import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { authenticatedSessionHandler, server } from "../test/server";
import { renderApp } from "../test/render";

describe("InterviewDetailPage", () => {
  it("submits one answer with a stable key and keeps protected fields hidden", async () => {
    const user = userEvent.setup();
    let submitted = false;
    let body: unknown = null;
    let key: string | null = null;
    const interview = () => ({
      interview_id: "interview-live-1",
      state: "in_progress",
      direction: "backend",
      configuration: {
        direction: "backend",
        difficulty: "balanced",
        topic_keys: [],
      },
      server_time: "2026-10-18T08:10:00Z",
      deadline_at: "2026-10-18T08:40:00Z",
      ended_at: null,
      current_turn: submitted
        ? {
            id: "turn-1",
            type: "main",
            depth: 0,
            question_text: "如何设计幂等接口？",
            topic_key: "api_idempotency",
            difficulty: "medium",
            state: "scoring",
          }
        : {
            id: "turn-1",
            type: "main",
            depth: 0,
            question_text: "如何设计幂等接口？",
            topic_key: "api_idempotency",
            difficulty: "medium",
            state: "awaiting_answer",
          },
      submitted_turns: [],
      progress: {
        main_questions_completed: 0,
        main_questions_total: 5,
        main_questions_remaining: 5,
        current_follow_up_chain: "awaiting_answer",
        remaining_seconds: 1800,
      },
    });
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/interviews/interview-live-1", () =>
        HttpResponse.json(interview()),
      ),
      http.post(
        "*/api/v1/interviews/interview-live-1/turns/turn-1/answer",
        async ({ request }) => {
          submitted = true;
          body = await request.json();
          key = request.headers.get("Idempotency-Key");
          return HttpResponse.json(
            {
              turn_id: "turn-1",
              state: "scoring",
              accepted_at: "2026-10-18T08:10:05Z",
              progress: {
                main_questions_completed: 0,
                main_questions_total: 5,
                main_questions_remaining: 5,
                current_follow_up_chain: "scoring",
                remaining_seconds: 1795,
              },
              next_action: "wait",
            },
            { status: 202 },
          );
        },
      ),
    );
    renderApp("/interviews/interview-live-1");

    expect(
      await screen.findByRole("heading", { name: "如何设计幂等接口？" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("参考答案")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("你的回答"), "使用幂等键和唯一约束。");
    await user.click(screen.getByRole("button", { name: "提交回答" }));

    expect(
      await screen.findByRole("heading", {
        name: "回答已记录，正在准备下一题",
      }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(body).toEqual({
        answer: "使用幂等键和唯一约束。",
        client_submitted_at: expect.any(String),
      });
    });
    expect(key).toBeTruthy();
    expect(screen.queryByText(/88/)).not.toBeInTheDocument();
  });

  it("unlocks the report only in terminal state and renders the turn tree", async () => {
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/interviews/interview-complete-1", () =>
        HttpResponse.json({
          interview_id: "interview-complete-1",
          state: "completed",
          direction: "backend",
          configuration: {
            direction: "backend",
            difficulty: "balanced",
            topic_keys: [],
          },
          server_time: "2026-10-18T08:40:00Z",
          deadline_at: "2026-10-18T08:40:00Z",
          ended_at: "2026-10-18T08:35:00Z",
          current_turn: null,
          submitted_turns: [],
          progress: {
            main_questions_completed: 5,
            main_questions_total: 5,
            main_questions_remaining: 0,
            current_follow_up_chain: "completed",
            remaining_seconds: 0,
          },
        }),
      ),
      http.get("*/api/v1/interviews/interview-complete-1/report", () =>
        HttpResponse.json({
          interview_id: "interview-complete-1",
          state: "completed",
          direction: "backend",
          scoring_status: "complete",
          server_time: "2026-10-18T08:40:00Z",
          summary: {
            main_question_count: 5,
            follow_up_count: 1,
            passed_count: 4,
            failed_count: 1,
          },
          turns: [
            {
              id: "turn-1",
              parent_turn_id: null,
              type: "main",
              depth: 0,
              question_text: "如何设计幂等接口？",
              topic_key: "api_idempotency",
              difficulty: "medium",
              result: "passed",
              score_total: 88,
              score_band: "85_plus",
              score_breakdown: {},
              loss_reasons: [],
              reference_answer: "参考答案只在报告里出现。",
              submitted_at: "2026-10-18T08:20:00Z",
            },
            {
              id: "turn-2",
              parent_turn_id: "turn-1",
              type: "follow_up",
              depth: 1,
              question_text: "并发重放如何处理？",
              topic_key: "api_idempotency",
              difficulty: "hard",
              result: "failed",
              score_total: 62,
              score_band: "below_70",
              score_breakdown: {},
              loss_reasons: ["未说明唯一约束"],
              reference_answer: "唯一约束与响应回放。",
              submitted_at: "2026-10-18T08:24:00Z",
            },
          ],
          wrong_questions: [],
          weak_points: [],
        }),
      ),
    );
    renderApp("/interviews/interview-complete-1");

    expect(await screen.findByRole("heading", { name: "面试报告" })).toBeInTheDocument();
    expect(
      await screen.findByText("参考答案只在报告里出现。"),
    ).toBeInTheDocument();
    expect(screen.getByText("追问 1")).toBeInTheDocument();
    expect(screen.getByText(/4/)).toBeInTheDocument();
  });
});

