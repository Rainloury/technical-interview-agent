import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { authenticatedSessionHandler, server } from "../test/server";
import { renderApp } from "../test/render";

describe("ReviewPage", () => {
  it("requires confirmation and sends the delete-all request with CSRF and idempotency", async () => {
    const user = userEvent.setup();
    let key: string | null = null;
    let csrf: string | null = null;
    let deleted = false;
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/wrong-questions", () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get("*/api/v1/me/data-deletion", () =>
        HttpResponse.json(
          deleted
            ? {
                request_id: "delete-1",
                state: "completed",
                scope: ["resume_tasks"],
                result: {},
                error_code: null,
                created_at: "2026-10-18T08:00:00Z",
                updated_at: "2026-10-18T08:01:00Z",
                completed_at: "2026-10-18T08:01:00Z",
              }
            : null,
        ),
      ),
      http.delete("*/api/v1/me/data", ({ request }) => {
        deleted = true;
        key = request.headers.get("Idempotency-Key");
        csrf = request.headers.get("X-CSRF-Token");
        return HttpResponse.json(
          {
            request_id: "delete-1",
            state: "requested",
            accepted_at: "2026-10-18T08:00:00Z",
          },
          { status: 202 },
        );
      }),
    );
    document.cookie = "interview_csrf=review-csrf; path=/";
    renderApp("/reviews");

    await user.click(
      await screen.findByRole("button", { name: "删除全部数据" }),
    );
    expect(
      screen.getByRole("heading", { name: "确认删除全部业务数据？" }),
    ).toBeInTheDocument();
    expect(key).toBeNull();

    await user.click(screen.getByRole("button", { name: "确认删除" }));
    await waitFor(() => expect(key).toBeTruthy());
    expect(csrf).toBe("review-csrf");
    expect(
      await screen.findByText("删除已完成"),
    ).toBeInTheDocument();
  });
});

