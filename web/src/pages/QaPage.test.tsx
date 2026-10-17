import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

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
});
