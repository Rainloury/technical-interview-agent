import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderApp } from "../test/render";

describe("RegisterPage", () => {
  it("shows the neutral acceptance and directs the user to login", async () => {
    const user = userEvent.setup();
    renderApp("/register");

    await user.type(await screen.findByLabelText("邮箱"), "new@example.com");
    await user.type(screen.getByLabelText("密码"), "correct horse battery staple");
    await user.type(screen.getByLabelText("确认密码"), "correct horse battery staple");
    await user.click(screen.getByRole("button", { name: "创建账号" }));

    expect(
      await screen.findByText(/注册请求已受理/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/已有账号的密码不会被本次注册修改/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "前往登录" })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  it("blocks mismatched passwords", async () => {
    const user = userEvent.setup();
    renderApp("/register");

    await user.type(await screen.findByLabelText("邮箱"), "new@example.com");
    await user.type(screen.getByLabelText("密码"), "correct horse battery staple");
    await user.type(screen.getByLabelText("确认密码"), "different password");
    await user.click(screen.getByRole("button", { name: "创建账号" }));

    expect(screen.getByText("两次输入的密码不一致。")).toBeInTheDocument();
  });
});
