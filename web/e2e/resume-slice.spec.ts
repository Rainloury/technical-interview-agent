import { spawn, type ChildProcessByStdio } from "node:child_process";
import type { Readable } from "node:stream";

import { expect, test, type Page } from "@playwright/test";

const password = "correct horse battery staple";
const resumeFilename = "e2e-backend-resume.pdf";
const protectedAnswer = "仅用于服务端评分的参考答案，不应公开。";
const protectedRubric = "正确性";
interface WorkerProcess {
  process: ChildProcessByStdio<null, Readable, Readable>;
  diagnostics: () => string;
}
const resumePdf = Buffer.from(
  "JVBERi0xLjMKJeLjz9MKMSAwIG9iago8PAovUHJvZHVjZXIgKHB5cGRmKQo+PgplbmRvYmoKMiAwIG9iago8PAovVHlwZSAvUGFnZXMKL0NvdW50IDEKL0tpZHMgWyA0IDAgUiBdCj4+CmVuZG9iagozIDAgb2JqCjw8Ci9UeXBlIC9DYXRhbG9nCi9QYWdlcyAyIDAgUgo+PgplbmRvYmoKNCAwIG9iago8PAovVHlwZSAvUGFnZQovUmVzb3VyY2VzIDw8Ci9Gb250IDw8Ci9GMSA1IDAgUgo+Pgo+PgovTWVkaWFCb3ggWyAwLjAgMC4wIDYxMiA3OTIgXQovUGFyZW50IDIgMCBSCi9Db250ZW50cyA2IDAgUgo+PgplbmRvYmoKNSAwIG9iago8PAovVHlwZSAvRm9udAovU3VidHlwZSAvVHlwZTEKL0Jhc2VGb250IC9IZWx2ZXRpY2EKPj4KZW5kb2JqCjYgMCBvYmoKPDwKL0xlbmd0aCA5Ngo+PgpzdHJlYW0KQlQgL0YxIDEyIFRmIDcyIDcyMCBUZCAoRTJFIENhbmRpZGF0ZSBQeXRob24gUG9zdGdyZVNRTCBhc3luY2hyb25vdXMgYm91bmRlZCB3b3JrZXIgcmV0cnkpIFRqIEVUCmVuZHN0cmVhbQplbmRvYmoKeHJlZgowIDcKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDE1IDAwMDAwIG4gCjAwMDAwMDAwNTQgMDAwMDAgbiAKMDAwMDAwMDExMyAwMDAwMCBuIAowMDAwMDAwMTYyIDAwMDAwIG4gCjAwMDAwMDI5NCAwMDAwMCBuIAowMDAwMDAwMzY0IDAwMDAwIG4gCnRyYWlsZXIKPDwKL1NpemUgNwovUm9vdCAzIDAgUgovSW5mbyAxIDAgUgo+PgpzdGFydHhyZWYKNTEwCiUlRU9GCg==",
  "base64",
);

function emailFor(projectName: string): string {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `resume-${projectName}-${suffix}@example.com`;
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
    const onData = (chunk: Buffer) => {
      void chunk;
      if (output.includes("ready")) {
        clearTimeout(timeout);
        child.stdout.off("data", onData);
        resolve();
      }
    };
    const onError = (error: Error) => {
      clearTimeout(timeout);
      reject(error);
    };
    child.once("error", onError);
    child.once("exit", (code: number | null) => {
      if (!output.includes("ready")) {
        clearTimeout(timeout);
        reject(
          new Error(`deterministic worker exited before ready (code ${String(code)}): ${output}`),
        );
      }
    });
    child.stdout.on("data", onData);
    if (output.includes("ready")) {
      onData(Buffer.alloc(0));
    }
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

async function clearBrowserSession(page: Page): Promise<void> {
  await page.context().clearCookies();
  await page.goto("/login");
}

test("uploads a resume, renders 10 grounded questions, and deletes its source", async ({
  page,
}, testInfo) => {
  test.setTimeout(90_000);
  const email = emailFor(testInfo.project.name);
  let worker: WorkerProcess | null = null;

  try {
    worker = await startDeterministicWorker(`${testInfo.config.rootDir}/..`);
    await clearBrowserSession(page);
    await registerAndLogin(page, email);

    await page.goto("/resumes/new");
    await page.getByLabel("简历文件").setInputFiles({
      name: resumeFilename,
      mimeType: "application/pdf",
      buffer: resumePdf,
    });
    await page.getByRole("button", { name: "开始分析" }).click();
    await expect(page).toHaveURL(/\/resumes\/[0-9a-f-]+$/);

    try {
      await expect(page.getByText("10 道")).toBeVisible({ timeout: 25_000 });
    } catch (error) {
      throw new Error(
        `${error instanceof Error ? error.message : String(error)}\nWorker diagnostics:\n${worker.diagnostics()}`,
      );
    }
    await expect(page.getByText("结构化分析")).toBeVisible();
    await expect(page.getByText("Python", { exact: true })).toBeVisible();
    await expect(page.getByText("PostgreSQL", { exact: true })).toBeVisible();
    await expect(page.getByText("有界任务平台", { exact: true })).toBeVisible();
    await expect(
      page.getByText("E2E问题 1：如何设计有界任务的并发与重试？"),
    ).toBeVisible();
    await expect(page.locator(".question-card")).toHaveCount(10);

    const pageText = await page.locator("body").innerText();
    expect(pageText).not.toContain(protectedAnswer);
    expect(pageText).not.toContain(protectedRubric);
    expect(pageText).not.toContain("评分标准");
    expect(pageText).not.toContain(resumeFilename);

    const deleteResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "DELETE" &&
        /\/api\/v1\/resumes\/[0-9a-f-]+\/source$/.test(response.url()),
    );
    await page.getByRole("button", { name: "删除原始简历" }).click();
    await page.getByRole("button", { name: "确认删除" }).click();
    expect((await deleteResponse).status()).toBe(204);
    await expect(
      page.getByRole("heading", { name: "原始简历已删除" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "删除原始简历" })).toHaveCount(0);
  } finally {
    await stopWorker(worker);
  }
});
