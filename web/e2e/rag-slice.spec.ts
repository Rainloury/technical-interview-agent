import { spawn, type ChildProcessByStdio } from "node:child_process";
import type { Readable } from "node:stream";

import { expect, test, type Page } from "@playwright/test";

const password = "correct horse battery staple";
const webUrl = process.env.WEB_URL ?? "http://127.0.0.1:3101";
const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8100";
const question = "私有重试手册如何限制次数并避免重复提交？";
const documentTitle = "私有重试手册";
const documentContent =
  "# 有界重试\n\n" +
  "私有重试手册规定：必须限制总尝试次数，使用指数退避和抖动，并通过幂等键避免重复提交。\n";

interface WorkerProcess {
  process: ChildProcessByStdio<null, Readable, Readable>;
  diagnostics: () => string;
}

function emailFor(projectName: string): string {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `rag-${projectName}-${suffix}@example.com`;
}

async function registerAndLogin(page: Page, email: string): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("textbox", { name: "确认密码", exact: true }).fill(password);
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(
    page.getByText("注册请求已受理。请使用原密码登录；已有账号的密码不会被本次注册修改。"),
  ).toBeVisible();
  await page.getByRole("link", { name: "前往登录" }).click();
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/workspace$/);
}

async function startWorker(cwd: string): Promise<WorkerProcess> {
  const child = spawn(
    "uv",
    ["run", "python", "-m", "scripts.e2e_resume_worker"],
    { cwd, env: process.env, stdio: ["ignore", "pipe", "pipe"] },
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
      () => reject(new Error(`deterministic worker did not become ready: ${output}`)),
      30_000,
    );
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
  if (!worker || worker.process.exitCode !== null || worker.process.signalCode !== null) {
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

test("uploads a private document, cites it, and marks it deleted in history", async ({
  page,
}, testInfo) => {
  test.setTimeout(120_000);
  let worker: WorkerProcess | null = null;
  try {
    worker = await startWorker(`${testInfo.config.rootDir}/..`);
    await registerAndLogin(page, emailFor(testInfo.project.name));

    await page.goto("/documents");
    await expect(page.getByRole("heading", { name: "内部资料" })).toBeVisible();
    await page.getByLabel("资料标题").fill(documentTitle);
    await page.getByLabel("资料文件").setInputFiles({
      name: "private-retry.md",
      mimeType: "text/markdown",
      buffer: Buffer.from(documentContent),
    });
    await page.getByRole("button", { name: "上传资料" }).click();

    try {
      await expect(page.getByText(documentTitle, { exact: true })).toBeVisible();
      await expect(page.getByText("可检索", { exact: true })).toBeVisible({
        timeout: 30_000,
      });
    } catch (error) {
      throw new Error(
        `${error instanceof Error ? error.message : String(error)}\nWorker diagnostics:\n${worker.diagnostics()}`,
      );
    }

    await page.goto("/qa");
    await page.getByLabel("技术问题").fill(question);
    await page.getByRole("button", { name: "开始检索" }).click();
    await expect(page).toHaveURL(/\/qa\/[0-9a-f-]+$/);
    const qaUrl = page.url();
    try {
      await expect(page.getByRole("heading", { name: "回答" })).toBeVisible({
        timeout: 30_000,
      });
      await expect(page.getByText(documentTitle, { exact: true })).toBeVisible();
      await expect(page.getByText("个人资料", { exact: true })).toBeVisible();
    } catch (error) {
      throw new Error(
        `${error instanceof Error ? error.message : String(error)}\nWorker diagnostics:\n${worker.diagnostics()}`,
      );
    }

    await page.goto("/documents");
    await page.getByRole("button", { name: `删除 ${documentTitle}` }).click();
    await page.getByRole("button", { name: "确认删除" }).click();
    await expect(
      page.getByRole("main").getByText(documentTitle, { exact: true }),
    ).toHaveCount(0);

    await page.goto(qaUrl);
    await expect(page.getByRole("heading", { name: "回答" })).toBeVisible();
    await expect(page.getByText(documentTitle, { exact: true })).toBeVisible();
    await expect(page.getByText("来源已删除", { exact: true })).toBeVisible();

    const listing = await page.request.get(
      `${apiUrl}/api/v1/documents?limit=20`,
      { headers: { Origin: webUrl } },
    );
    expect(listing.status()).toBe(200);
    const listingPayload = (await listing.json()) as {
      items: { title: string }[];
    };
    expect(
      listingPayload.items.some((item) => item.title === documentTitle),
    ).toBe(false);

    await page.goto("/qa");
    await page.getByLabel("技术问题").fill(question);
    await page.getByRole("button", { name: "开始检索" }).click();
    await expect(page).toHaveURL(/\/qa\/[0-9a-f-]+$/);
    await expect(page.getByRole("heading", { name: "回答" })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText(documentTitle, { exact: true })).toHaveCount(0);
  } finally {
    await stopWorker(worker);
  }
});
