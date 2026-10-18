import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import process from "node:process";

const dataEncryptionKey =
  process.env.DATA_ENCRYPTION_KEY ?? randomBytes(32).toString("base64url");
const webUrl = process.env.WEB_URL ?? "http://127.0.0.1:3101";
const workerHealthFile =
  process.env.WORKER_HEALTH_FILE ??
  "/private/tmp/technical-interview-agent-e2e-worker-health";
const serverEnvironment = {
  ...process.env,
  DATA_ENCRYPTION_KEY: dataEncryptionKey,
  MAIL_LOCAL_RESET_FILE:
    process.env.MAIL_LOCAL_RESET_FILE ??
    "/private/tmp/technical-interview-agent-password-reset.json",
  RESUME_STORAGE_DIR:
    process.env.RESUME_STORAGE_DIR ??
    "/private/tmp/technical-interview-agent-resume-files",
  WORKER_HEALTH_FILE: workerHealthFile,
};
delete serverEnvironment.SMTP_HOST;
delete serverEnvironment.OSS_ENDPOINT;
delete serverEnvironment.OSS_BUCKET;
delete serverEnvironment.OSS_ACCESS_KEY_ID;
delete serverEnvironment.OSS_ACCESS_KEY_SECRET;
delete serverEnvironment.RESUME_STORAGE_BACKEND;
const server = spawn("uv", ["run", "python", "-m", "scripts.run_e2e_servers"], {
  cwd: "..",
  env: serverEnvironment,
  stdio: ["ignore", "pipe", "inherit"],
});

const stop = () => {
  if (!server.killed) {
    server.kill("SIGTERM");
  }
};

process.on("SIGINT", stop);
process.on("SIGTERM", stop);

const ready = new Promise((resolve, reject) => {
  server.once("error", reject);
  server.once("exit", (code) => {
    reject(new Error(`E2E servers exited before ready (code ${String(code)})`));
  });
  server.stdout.on("data", (chunk) => {
    if (String(chunk).includes("ready")) {
      resolve();
    }
  });
});

try {
  await ready;
  const tests = spawn("npx", ["playwright", "test"], {
    env: {
      ...process.env,
      DATA_ENCRYPTION_KEY: dataEncryptionKey,
      PLAYWRIGHT_EXTERNAL_SERVERS: "1",
      COOKIE_SECURE: "false",
      APP_ALLOWED_ORIGINS: JSON.stringify([webUrl]),
      CSRF_ALLOWED_ORIGINS: JSON.stringify([webUrl]),
      PASSWORD_RESET_BASE_URL: `${webUrl}/reset-password`,
      WORKER_HEALTH_FILE: workerHealthFile,
    },
    stdio: "inherit",
  });
  const code = await new Promise((resolve) => tests.on("exit", resolve));
  process.exitCode = code ?? 1;
} finally {
  stop();
}
