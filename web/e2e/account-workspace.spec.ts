import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { promisify } from "node:util";

import { expect, test, type Page } from "@playwright/test";

const run = promisify(execFile);
const password = "correct horse battery staple";
const newPassword = "new correct horse battery staple";
const resetFile =
  process.env.MAIL_LOCAL_RESET_FILE ??
  "/private/tmp/technical-interview-agent-password-reset.json";

function emailFor(projectName: string): string {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `e2e-${projectName}-${suffix}@example.com`;
}

test("shows the public GitHub repository entry on the home screen", async ({ page }) => {
  await page.goto("/login");

  const githubLink = page.getByRole("link", { name: "开源仓库" }).filter({ visible: true });
  await expect(githubLink).toBeVisible();
  await expect(githubLink).toHaveAttribute(
    "href",
    "https://github.com/Rainloury/technical-interview-agent",
  );
  await expect(githubLink.locator('[data-github-mark="true"]')).toBeVisible();
});

async function register(page: Page, email: string): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("textbox", { name: "确认密码", exact: true }).fill(password);
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(
    page.getByText("注册请求已受理。请使用原密码登录；已有账号的密码不会被本次注册修改。"),
  ).toBeVisible();
}

async function login(page: Page, email: string, value = password): Promise<void> {
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码", { exact: true }).fill(value);
  await page.getByRole("button", { name: "登录", exact: true }).click();
}

async function logout(page: Page, isMobile: boolean): Promise<void> {
  if (isMobile) {
    await page.getByRole("button", { name: "打开导航" }).click();
  }
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

async function waitForResetLink(email: string): Promise<string> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 120; attempt += 1) {
    try {
      const payload = JSON.parse(await readFile(resetFile, "utf8")) as {
        email?: string;
        reset_url?: string;
      };
      if (payload.email === email && payload.reset_url) {
        return payload.reset_url;
      }
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`reset link for ${email} was not written: ${String(lastError)}`);
}

test("account, workspace, history, and password recovery journey", async ({
  page,
}, testInfo) => {
  const email = emailFor(testInfo.project.name);
  const isMobile =
    testInfo.project.name === "mobile-chrome" ||
    testInfo.project.name === "mobile-webkit-iphone13";

  await page.goto("/history?type=qa");
  await expect(page).toHaveURL(
    new RegExp(`/login\\?returnTo=${encodeURIComponent("/history?type=qa")}`),
  );

  await register(page, email);
  await page.getByRole("link", { name: "前往登录" }).click();
  await login(page, email);
  await expect(page).toHaveURL(/\/workspace$/);
  await expect(page.getByText("工作台还很安静")).toBeVisible();

  const cookies = await page.context().cookies();
  const session = cookies.find((cookie) => cookie.name === "interview_session");
  const csrf = cookies.find((cookie) => cookie.name === "interview_csrf");
  expect(session?.httpOnly).toBe(true);
  expect(session?.secure).toBe(false);
  expect(csrf?.httpOnly).toBe(false);
  expect(csrf?.secure).toBe(false);

  await page.getByRole("link", { name: "全部历史" }).click();
  for (const tab of ["模拟面试", "简历任务", "技术问答", "错题"]) {
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.getByRole("tab", { name: tab })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  }

  if (isMobile) {
    await page.getByRole("button", { name: "打开导航" }).click();
    const closeNavigation = page.getByRole("button", { name: "关闭导航" }).first();
    await expect(closeNavigation).toBeVisible();
    await closeNavigation.click();
  }

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(overflow).toBe(false);

  await logout(page, isMobile);

  await run("uv", ["run", "python", "-m", "scripts.prepare_e2e", email], {
    cwd: testInfo.config.rootDir + "/..",
  });

  await login(page, email);
  await expect(page).toHaveURL(/\/workspace$/);
  await page.goto("/history?type=interview");
  await expect(page.locator(".history-row")).toHaveCount(10);
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(page.locator(".history-row")).toHaveCount(12);
  await expect(page.getByRole("button", { name: "加载更多" })).toHaveCount(0);

  await logout(page, isMobile);
  await page.getByRole("link", { name: "忘记密码？" }).click();
  await page.getByLabel("邮箱").fill(email);
  await page.getByRole("button", { name: "发送重置链接" }).click();
  await expect(
    page.getByText(
      "请求已受理。如果该邮箱对应账号，重置邮件将很快送达。请检查收件箱和垃圾邮件。",
    ),
  ).toBeVisible();

  const resetUrl = await waitForResetLink(email);
  await page.goto(resetUrl);
  await page.getByRole("textbox", { name: "新密码", exact: true }).fill(newPassword);
  await page
    .getByRole("textbox", { name: "确认新密码", exact: true })
    .fill(newPassword);
  await page.getByRole("button", { name: "更新密码" }).click();
  await expect(
    page.getByText("密码已更新，旧会话已失效。请使用新密码登录。"),
  ).toBeVisible();
  await page.getByRole("button", { name: "前往登录" }).click();
  await login(page, email, newPassword);
  await expect(page).toHaveURL(/\/workspace$/);
});
