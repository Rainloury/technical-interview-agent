import { spawn, type ChildProcessByStdio } from "node:child_process";
import type { Readable } from "node:stream";

import { expect, test, type Page } from "@playwright/test";

const password = "correct horse battery staple";
const webUrl = process.env.WEB_URL ?? "http://127.0.0.1:3101";

interface WorkerProcess {
  process: ChildProcessByStdio<null, Readable, Readable>;
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
    const timeout = setTimeout(() => reject(new Error(output)), 30_000);
    const onData = () => {
      if (output.includes("ready")) {
        clearTimeout(timeout);
        resolve();
      }
    };
    child.once("error", reject);
    child.stdout.on("data", onData);
    child.stderr.on("data", onData);
  });
  return { process: child };
}

async function stopWorker(worker: WorkerProcess | null): Promise<void> {
  if (!worker || worker.process.exitCode !== null) {
    return;
  }
  worker.process.kill("SIGTERM");
  await Promise.race([
    new Promise<void>((resolve) => worker.process.once("exit", () => resolve())),
    new Promise<void>((resolve) => setTimeout(resolve, 5_000)),
  ]);
}

test("requests account deletion and hides business history immediately", async ({
  page,
}, testInfo) => {
  test.setTimeout(90_000);
  let worker: WorkerProcess | null = null;
  try {
    worker = await startWorker(`${testInfo.config.rootDir}/..`);
    await registerAndLogin(
      page,
      `privacy-${testInfo.project.name}-${Date.now()}@example.com`,
    );

    await page.goto("/reviews");
    await page.getByRole("button", { name: "删除全部数据" }).click();
    await expect(
      page.getByRole("heading", { name: "确认删除全部业务数据？" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "确认删除" }).click();
    await expect(page.getByText("删除已完成")).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(".review-list")).toHaveCount(0);

    await expect
      .poll(async () => {
        const response = await page.request.get(
          `${process.env.API_URL ?? "http://127.0.0.1:8100"}/api/v1/dashboard`,
          { headers: { Origin: webUrl } },
        );
        return response.status();
      })
      .toBe(401);

    await page.goto("/workspace");
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("heading", { name: "登录工作台" })).toBeVisible();
  } finally {
    await stopWorker(worker);
  }
});

