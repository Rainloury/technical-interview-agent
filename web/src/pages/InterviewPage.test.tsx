import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { authenticatedSessionHandler, server } from "../test/server";
import { renderApp } from "../test/render";

describe("InterviewPage", () => {
  it("creates a bounded interview configuration and opens the ready page", async () => {
    const user = userEvent.setup();
    let body: unknown = null;
    let key: string | null = null;
    server.use(
      authenticatedSessionHandler(),
      http.post("*/api/v1/interviews", async ({ request }) => {
        body = await request.json();
        key = request.headers.get("Idempotency-Key");
        return HttpResponse.json(
          {
            interview_id: "interview-created-1",
            state: "created",
            main_question_count: 5,
            deadline_at: null,
            configuration: {
              direction: "frontend",
              difficulty: "challenge",
              topic_keys: ["event_loop"],
            },
          },
          { status: 201 },
        );
      }),
      http.get("*/api/v1/interviews/interview-created-1", () =>
        HttpResponse.json({
          interview_id: "interview-created-1",
          state: "created",
          direction: "frontend",
          configuration: {
            direction: "frontend",
            difficulty: "challenge",
            topic_keys: ["event_loop"],
          },
          server_time: "2026-10-18T08:00:00Z",
          deadline_at: null,
          ended_at: null,
          current_turn: null,
          submitted_turns: [],
          progress: {
            main_questions_completed: 0,
            main_questions_total: 5,
            main_questions_remaining: 5,
            current_follow_up_chain: null,
            remaining_seconds: 2400,
          },
        }),
      ),
    );
    renderApp("/interviews");

    await user.click(await screen.findByLabelText("前端方向"));
    await user.click(screen.getByLabelText("进阶"));
    await user.click(screen.getByRole("button", { name: "事件循环" }));
    await user.click(screen.getByRole("button", { name: "创建并开始" }));

    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/interviews/interview-created-1",
      );
    });
    expect(body).toEqual({
      direction: "frontend",
      difficulty: "challenge",
      topic_keys: ["event_loop"],
    });
    expect(key).toBeTruthy();
    expect(
      await screen.findByRole("heading", { name: "开始后不会暂停" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/5 个主问题/)).toBeInTheDocument();
  });

  it("starts an interview after explicit confirmation", async () => {
    const user = userEvent.setup();
    let started = false;
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/interviews/interview-ready-1", () =>
        HttpResponse.json({
          interview_id: "interview-ready-1",
          state: started ? "in_progress" : "created",
          direction: "backend",
          configuration: {
            direction: "backend",
            difficulty: "balanced",
            topic_keys: [],
          },
          server_time: "2026-10-18T08:00:00Z",
          deadline_at: started ? "2026-10-18T08:40:00Z" : null,
          ended_at: null,
          current_turn: null,
          submitted_turns: [],
          progress: {
            main_questions_completed: 0,
            main_questions_total: 5,
            main_questions_remaining: 5,
            current_follow_up_chain: started ? "awaiting_answer" : null,
            remaining_seconds: 2400,
          },
        }),
      ),
      http.post("*/api/v1/interviews/interview-ready-1/start", () => {
        started = true;
        return HttpResponse.json({
          interview_id: "interview-ready-1",
          state: "in_progress",
          server_time: "2026-10-18T08:00:01Z",
          deadline_at: "2026-10-18T08:40:01Z",
          current_turn: null,
          progress: {
            main_questions_completed: 0,
            main_questions_total: 5,
            main_questions_remaining: 5,
            current_follow_up_chain: "awaiting_answer",
            remaining_seconds: 2400,
          },
        });
      }),
    );
    renderApp("/interviews/interview-ready-1");

    await user.click(await screen.findByRole("button", { name: "开始面试" }));
    expect(await screen.findByText("正在准备下一题")).toBeInTheDocument();
    expect(screen.getByLabelText("剩余时间")).toHaveTextContent("40:00");
  });
});

