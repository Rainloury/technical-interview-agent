import { spawn, type ChildProcessByStdio } from "node:child_process";
import type { Readable } from "node:stream";

import { expect, test, type Page } from "@playwright/test";

const password = "correct horse battery staple";
const question = "如何设计有界重试并避免重复提交？";
const answer =
  "有界重试应设置次数上限，使用指数退避与抖动，并通过幂等键避免重复提交。";
const webUrl = process.env.WEB_URL ?? "http://127.0.0.1:3101";

interface WorkerProcess {
  process: ChildProcessByStdio<null, Readable, Readable>;
  diagnostics: () => string;
}

function emailFor(projectName: string): string {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `qa-${projectName}-${suffix}@example.com`;
}

async function registerAndLogin(page: Page, email: string): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("textbox", { name: "确认密码", exact: true }).fill(password);
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(
    page.getByText("注册请求已受理。请前往登录；该结果不会透露账号是否已存在。"),
  ).toBeVisible();
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
    const timeout = setTimeout(() => {
      reject(new Error(`deterministic worker did not become ready: ${output}`));
    }, 30_000);
    const onData = () => {
      if (output.includes("ready")) {
        clearTimeout(timeout);
        resolve();
      }
    };
    child.once("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.once("exit", (code: number | null) => {
      if (!output.includes("ready")) {
        clearTimeout(timeout);
        reject(
          new Error(`deterministic worker exited before ready (code ${String(code)}): ${output}`),
        );
      }
    });
    child.stdout.on("data", onData);
    child.stderr.on("data", onData);
  });
  return { process: child, diagnostics: () => output };
}

async function stopWorker(worker: WorkerProcess | null): Promise<void> {
  if (
    !worker ||
    worker.process.exitCode !== null ||
    worker.process.signalCode !== null
  ) {
    return;
  }
  worker.process.kill("SIGTERM");
  await Promise.race([
    new Promise<void>((resolve) => worker.process.once("exit", () => resolve())),
    new Promise<void>((resolve) => setTimeout(resolve, 5_000)),
  ]);
  if (worker.process.exitCode === null && worker.process.signalCode === null) {
    worker.process.kill("SIGKILL");
  }
}

async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(overflow).toBe(false);
}

test("answers a question from published evidence and reopens it from history", async ({
  page,
}, testInfo) => {
  test.setTimeout(90_000);
  let worker: WorkerProcess | null = null;

  try {
    worker = await startDeterministicWorker(`${testInfo.config.rootDir}/..`);
    await registerAndLogin(page, emailFor(testInfo.project.name));

    await page
      .getByRole("main")
      .getByRole("link", { name: "技术问答" })
      .click();
    await expect(page).toHaveURL(/\/qa$/);
    await page.getByLabel("技术问题").fill(question);
    await page.getByRole("button", { name: "开始检索" }).click();
    await expect(page).toHaveURL(/\/qa\/[0-9a-f-]+$/);

    try {
      await expect(page.getByText(answer, { exact: true })).toBeVisible({
        timeout: 25_000,
      });
    } catch (error) {
      throw new Error(
        `${error instanceof Error ? error.message : String(error)}\nWorker diagnostics:\n${worker.diagnostics()}`,
      );
    }
    await expect(page.getByText("有界重试设计指南", { exact: true })).toBeVisible();
    await expect(page.getByText("evidence-1", { exact: true })).toBeVisible();
    await expect(page.getByText("资料支持", { exact: true })).toBeVisible();
    const pageText = await page.locator("body").innerText();
    expect(pageText).not.toContain("https://docs.example");
    expect(pageText).not.toContain(
      "1f4b4e3e-2f59-4a15-9a71-2fa3d7b94001",
    );
    expect(pageText.match(new RegExp(answer, "g"))).toHaveLength(1);
    await expectNoHorizontalOverflow(page);

    await page.reload();
    await expect(page.getByText(answer, { exact: true })).toBeVisible();
    expect((await page.locator("body").innerText()).match(new RegExp(answer, "g"))).toHaveLength(1);

    await page.goto("/history?type=qa");
    await expect(page.locator(".history-row")).toHaveCount(1);
    await page.getByRole("link", { name: `查看 ${question}` }).click();
    await expect(page).toHaveURL(/\/qa\/[0-9a-f-]+$/);
    await expect(page.getByText(answer, { exact: true })).toBeVisible();

    await page.goto("/workspace");
    await page.getByRole("link", { name: `查看 ${question}` }).click();
    await expect(page).toHaveURL(/\/qa\/[0-9a-f-]+$/);
    await expect(page.getByText(answer, { exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  } finally {
    await stopWorker(worker);
  }
});

test("replays the same idempotency key without creating a duplicate history record", async ({
  page,
}, testInfo) => {
  test.setTimeout(90_000);
  let worker: WorkerProcess | null = null;

  try {
    worker = await startDeterministicWorker(`${testInfo.config.rootDir}/..`);
    await registerAndLogin(page, emailFor(testInfo.project.name));

    const cookies = await page.context().cookies();
    const csrf = cookies.find((cookie) => cookie.name === "interview_csrf");
    expect(csrf?.value).toBeTruthy();
    const key = `qa-e2e-${testInfo.project.name}-${Date.now()}`;
    const url = `${process.env.API_URL ?? "http://127.0.0.1:8100"}/api/v1/qa`;

    const first = await page.request.post(url, {
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": key,
        Origin: webUrl,
        "X-CSRF-Token": csrf?.value ?? "",
      },
      data: { question, answer_preference: "concise" },
    });
    expect(first.status()).toBe(202);
    const firstPayload = (await first.json()) as { qa_request_id: string };

    const replay = await page.request.post(url, {
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": key,
        Origin: webUrl,
        "X-CSRF-Token": csrf?.value ?? "",
      },
      data: { question, answer_preference: "concise" },
    });
    expect(replay.status()).toBe(202);
    const replayPayload = (await replay.json()) as { qa_request_id: string };
    expect(replayPayload.qa_request_id).toBe(firstPayload.qa_request_id);

    await page.goto("/history?type=qa");
    await expect(page.locator(".history-row")).toHaveCount(1);
    await expectNoHorizontalOverflow(page);
  } finally {
    await stopWorker(worker);
  }
});
