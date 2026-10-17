import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import {
  authenticatedSessionHandler,
  emptyDashboard,
  server,
} from "../test/server";
import { renderApp } from "../test/render";

describe("WorkspacePage", () => {
  it("renders recent activity and the authenticated shell", async () => {
    server.use(authenticatedSessionHandler());
    renderApp("/workspace");

    expect(
      await screen.findByRole("heading", { name: "示例用户", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByText("后端简历.pdf")).toBeInTheDocument();
    expect(screen.getByText("后端方向")).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "上传简历" }).every(
        (link) => link.getAttribute("href") === "/resumes/new",
      ),
    ).toBe(true);
    expect(screen.getByRole("link", { name: "全部历史" })).toHaveAttribute(
      "href",
      "/history",
    );
    expect(screen.getByRole("link", { name: "查看 后端简历.pdf" })).toHaveAttribute(
      "href",
      "/resumes/task-1",
    );
    expect(
      screen.getByRole("link", { name: "查看 如何解释数据库索引？" }),
    ).toHaveAttribute("href", "/qa/task-2");
    expect(
      screen.getByRole("link", { name: "继续 后端方向" }),
    ).toHaveAttribute("href", "/interviews/interview-1");
    expect(screen.getByRole("link", { name: "历史记录" })).toHaveClass("nav-item");
  });

  it("renders the empty workspace without inventing activity", async () => {
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/dashboard", () => HttpResponse.json(emptyDashboard)),
    );
    renderApp("/workspace");

    expect(await screen.findByText("工作台还很安静")).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "上传简历" }).every(
        (link) => link.getAttribute("href") === "/resumes/new",
      ),
    ).toBe(true);
    expect(screen.getByRole("link", { name: "全部历史" })).toHaveAttribute(
      "href",
      "/history",
    );
  });

  it("redirects an expired session to login and keeps the target", async () => {
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/dashboard", () =>
        HttpResponse.json(
          {
            error: {
              code: "authentication_required",
              message: "请先登录",
              retryable: false,
            },
          },
          { status: 401 },
        ),
      ),
    );
    renderApp("/workspace");

    expect(await screen.findByRole("heading", { name: "登录工作台" })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/login?returnTo=%2Fworkspace",
    );
  });
});
