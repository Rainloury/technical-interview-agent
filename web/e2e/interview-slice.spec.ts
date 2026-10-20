import { spawn, type ChildProcessByStdio } from "node:child_process";
import type { Readable } from "node:stream";

import { expect, test, type Page } from "@playwright/test";

const password = "correct horse battery staple";
const webUrl = process.env.WEB_URL ?? "http://127.0.0.1:3101";

interface WorkerProcess {
  process: ChildProcessByStdio<null, Readable, Readable>;
  diagnostics: () => string;
}

function emailFor(projectName: string): string {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `interview-${projectName}-${suffix}@example.com`;
}

async function registerAndLogin(page: Page, email: string): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("textbox", { name: "确认密码", exact: true }).fill(password);
  await page.getByRole("button", { name: "创建账号" }).click();
  await page.getByRole("link", { name: "前往登录" }).click();
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/workspace$/);
}

async function startDeterministicWorker(cwd: string): Promise<WorkerProcess> {
  const child = spawn(
    "uv",
    ["run", "python", "-m", "scripts.e2e_resume_worker"],
    {
      cwd,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  let output = "";
  child.stdout.on("data", (chunk: Buffer) => {
    output += chunk.toString();
  });
  child.stderr.on("data", (chunk: Buffer) => {
    output += chunk.toString();
  });
  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(
      () => reject(new Error(`worker did not become ready: ${output}`)),
      30_000,
    );
    const onData = () => {
      if (output.includes("ready")) {
        clearTimeout(timeout);
        resolve();
      }
    };
    child.once("error", reject);
    child.once("exit", (code) => {
      if (!output.includes("ready")) {
        clearTimeout(timeout);
        reject(new Error(`worker exited (${String(code)}): ${output}`));
      }
    });
    child.stdout.on("data", onData);
    child.stderr.on("data", onData);
  });
  return { process: child, diagnostics: () => output };
}

async function stopWorker(worker: WorkerProcess | null): Promise<void> {
  if (!worker || worker.process.exitCode !== null || worker.process.signalCode !== null) {
    return;
  }
  worker.process.kill("SIGTERM");
  await Promise.race([
    new Promise<void>((resolve) => worker.process.once("exit", () => resolve())),
    new Promise<void>((resolve) => setTimeout(resolve, 5_000)),
  ]);
}

async function clearBrowserSession(page: Page): Promise<void> {
  await page.context().clearCookies();
  await page.goto("/login");
}

async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    ),
  ).toBe(false);
}

test("completes a bounded interview and unlocks the report", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  let worker: WorkerProcess | null = null;
  try {
    worker = await startDeterministicWorker(`${testInfo.config.rootDir}/..`);
    await clearBrowserSession(page);
    await registerAndLogin(page, emailFor(testInfo.project.name));

    await page
      .getByRole("main")
      .getByRole("link", { name: "模拟面试" })
      .click();
    await expect(page).toHaveURL(/\/interviews$/);
    await page.getByLabel("后端方向").check();
    await page.getByLabel("均衡").check();
    await page.getByRole("button", { name: "API 幂等" }).click();
    await page.getByRole("button", { name: "创建并开始" }).click();
    await expect(page).toHaveURL(/\/interviews\/[0-9a-f-]+$/);
    await page.getByRole("button", { name: "开始面试" }).click();

    await expect(
      page.getByRole("heading", {
        name: /如何设计有界重试并保证重复提交不会产生副作用/,
      }),
    ).toBeVisible({ timeout: 20_000 });
    await page
      .getByLabel("你的回答")
      .fill("使用幂等键、唯一约束和有界指数退避，并在失败时恢复已保存状态。");
    await page.getByRole("button", { name: "提交回答" }).click();
    await expect(
      page.getByRole("heading", { name: "回答已记录，正在准备下一题" }),
    ).toBeVisible();

    await expect(
      page.getByRole("heading", { name: /E2E 追问/ }),
    ).toBeVisible({ timeout: 20_000 });
    const body = await page.locator("body").innerText();
    expect(body).not.toContain("受保护参考答案");
    expect(body).not.toContain("score_total");
    await expectNoHorizontalOverflow(page);

    await page.getByRole("button", { name: "跳过此题" }).click();
    await expect(
      page.getByRole("heading", { name: "跳过当前追问？" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "确认结束" }).click();
    await expect(
      page.getByRole("heading", { name: /E2E 主问题 2/ }),
    ).toBeVisible({ timeout: 20_000 });

    const cookies = await page.context().cookies();
    const csrf = cookies.find((cookie) => cookie.name === "interview_csrf")?.value ?? "";
    const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8100";
    const interviewId = page.url().split("/").pop();
    const detail = await page.request.get(
      `${apiUrl}/api/v1/interviews/${interviewId}`,
      { headers: { Origin: webUrl } },
    );
    expect(detail.status()).toBe(200);
    const current = (await detail.json()) as { current_turn: { id: string } };
    const reportKey = `interview-e2e-${Date.now()}`;
    const answer = await page.request.post(
      `${apiUrl}/api/v1/interviews/${interviewId}/turns/${current.current_turn.id}/answer`,
      {
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": reportKey,
          Origin: webUrl,
          "X-CSRF-Token": csrf,
        },
        data: { answer: "使用唯一约束和响应回放保证并发安全。" },
      },
    );
    expect(answer.status()).toBe(202);
    await expect(
      page.getByRole("heading", { name: /E2E 追问/ }),
    ).toBeVisible({ timeout: 20_000 });
    await page.reload();
    await expect(
      page.getByRole("heading", { name: /E2E 追问/ }),
    ).toBeVisible({ timeout: 20_000 });
    await expectNoHorizontalOverflow(page);
  } finally {
    await stopWorker(worker);
  }
});

test("shows neutral progress without scores while an interview is live", async ({
  page,
}, testInfo) => {
  test.setTimeout(90_000);
  let worker: WorkerProcess | null = null;
  try {
    worker = await startDeterministicWorker(`${testInfo.config.rootDir}/..`);
    await clearBrowserSession(page);
    await registerAndLogin(page, emailFor(testInfo.project.name));
    await page.goto("/interviews");
    await page.getByRole("button", { name: "创建并开始" }).click();
    await page.getByRole("button", { name: "开始面试" }).click();
    await expect(
      page.getByRole("heading", { name: /E2E 主问题 1/ }),
    ).toBeVisible({ timeout: 20_000 });
    const body = await page.locator("body").innerText();
    expect(body).toContain("反馈在结束后解锁");
    expect(body).not.toContain("受保护参考答案");
    expect(body).not.toMatch(/\b(?:88|90|100)\b/);
    expect(await page.getByLabel("剩余时间").innerText()).toMatch(/\d+:\d{2}/);
    await expectNoHorizontalOverflow(page);
  } finally {
    await stopWorker(worker);
  }
});

