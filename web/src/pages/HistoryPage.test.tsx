import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import type { HistoryItem, HistoryPage } from "../api/types";
import { authenticatedSessionHandler, emptyHistory, server } from "../test/server";
import { renderApp } from "../test/render";

function item(index: number): HistoryItem {
  return {
    id: `interview-${index}`,
    type: "interview",
    title: `模拟面试 ${index}`,
    state: "ended",
    updated_at: `2026-10-${String(index).padStart(2, "0")}T06:00:00Z`,
  };
}

describe("HistoryPage", () => {
  it("loads the next cursor page on demand", async () => {
    const user = userEvent.setup();
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/history", ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        const page: HistoryPage =
          cursor === "next-page"
            ? { items: [item(2)], next_cursor: null }
            : { items: [item(1)], next_cursor: "next-page" };
        return HttpResponse.json(page);
      }),
    );
    renderApp("/history?type=interview");

    expect(await screen.findByText("模拟面试 1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /加载更多/ }));
    expect(await screen.findByText("模拟面试 2")).toBeInTheDocument();
  });

  it("switches collection and shows an empty state", async () => {
    const user = userEvent.setup();
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/history", () => HttpResponse.json(emptyHistory)),
    );
    renderApp("/history?type=interview");

    expect(await screen.findByText("暂无这类记录")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "技术问答" }));
    expect(await screen.findByText("暂无这类记录")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "技术问答" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("links resume history rows to the resume detail page", async () => {
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/history", () =>
        HttpResponse.json({
          items: [
            {
              id: "resume-history-1",
              type: "resume",
              title: "高级后端简历.pdf",
              state: "completed",
              updated_at: "2026-10-17T08:00:00Z",
            },
          ],
          next_cursor: null,
        } satisfies HistoryPage),
      ),
    );
    renderApp("/history?type=resume");

    expect(await screen.findByText("高级后端简历.pdf")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "查看 高级后端简历.pdf" }),
    ).toHaveAttribute("href", "/resumes/resume-history-1");
  });
});
