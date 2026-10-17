import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { loginFlowHandlers, server } from "../test/server";
import { renderApp } from "../test/render";

describe("LoginPage", () => {
  it("validates credentials before sending a request", async () => {
    let requests = 0;
    server.use(
      http.post("*/api/v1/auth/login", () => {
        requests += 1;
        return HttpResponse.json({});
      }),
    );
    const user = userEvent.setup();
    renderApp("/login");

    await user.click(await screen.findByRole("button", { name: "登录" }));

    expect(screen.getByText("请输入有效的邮箱地址。")).toBeInTheDocument();
    expect(screen.getByText("请输入密码。")).toBeInTheDocument();
    expect(requests).toBe(0);
  });

  it("signs in and enters the requested workspace", async () => {
    server.use(...loginFlowHandlers());
    const user = userEvent.setup();
    renderApp("/login?returnTo=%2Fhistory");

    await user.type(await screen.findByLabelText("邮箱"), "user@example.com");
    await user.type(screen.getByLabelText("密码"), "correct horse battery staple");
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(screen.getAllByRole("heading", { name: "历史记录" }).length).toBeGreaterThan(0);
    });
  });
});
