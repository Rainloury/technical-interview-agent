import { spawn } from "node:child_process";
import console from "node:console";
import { randomBytes } from "node:crypto";
import process from "node:process";
import { clearTimeout, setTimeout } from "node:timers";

const terminateGraceMs = 5_000;
const killGraceMs = 5_000;
const testsTerminateGraceMs = 1_000;
const parseTimeout = (value, fallback) => {
  const timeout = Number(value ?? fallback);
  return Number.isFinite(timeout) && timeout > 0 ? timeout : fallback;
};
// E2E owns its ephemeral key so an invalid developer .env value cannot break
// password-reset flows, and the shared API/worker keep the same key.
const dataEncryptionKey = randomBytes(32).toString("base64url");
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
  detached: process.platform !== "win32",
  env: {
    ...serverEnvironment,
    ...(process.platform === "win32"
      ? {}
      : { PYTHONUNBUFFERED: "1" }),
  },
  stdio: ["ignore", "pipe", "inherit"],
});

let tests = null;

const isRunning = (child) =>
  child !== null && child.exitCode === null && child.signalCode === null;

const signal = (child, signalName) => {
  if (!isRunning(child)) {
    return;
  }
  try {
    if (process.platform === "win32") {
      child.kill(signalName);
    } else {
      process.kill(-child.pid, signalName);
    }
  } catch (error) {
    if (error.code !== "ESRCH") {
      throw error;
    }
  }
};

for (const event of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(event, () => {
    signal(tests, "SIGTERM");
    signal(server, "SIGTERM");
    process.exitCode = 128 + (event === "SIGINT" ? 2 : event === "SIGTERM" ? 15 : 1);
  });
}
process.on("exit", () => {
  signal(tests, "SIGKILL");
  signal(server, "SIGKILL");
});

const waitForReady = () =>
  new Promise((resolve, reject) => {
    const onExit = (code, signalName) => {
      reject(
        new Error(
          `E2E servers exited before ready (code ${String(code)}, signal ${String(signalName)})`,
        ),
      );
    };
    server.once("error", reject);
    server.once("exit", onExit);
    server.stdout.on("data", (chunk) => {
      if (!String(chunk).includes("ready")) {
        return;
      }
      server.removeListener("exit", onExit);
      resolve();
    });
  });

const waitForExit = async (child, timeoutMs) => {
  const deadline = Date.now() + timeoutMs;
  while (isRunning(child) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
};

const run = async () => {
  await waitForReady();
  tests = spawn("npx", ["playwright", "test"], {
    detached: process.platform !== "win32",
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
  const wrapperTimeout = parseTimeout(
    process.env.PLAYWRIGHT_WRAPPER_TIMEOUT_MS,
    900_000,
  );
  let timedOut = false;
  let timeout;
  const finished = new Promise((resolve, reject) => {
    tests.once("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    tests.once("exit", (code, signalName) => {
      clearTimeout(timeout);
      if (!timedOut) {
        process.exitCode = code ?? (signalName ? 1 : 0);
      }
      resolve();
    });
  });
  timeout = setTimeout(async () => {
    timedOut = true;
    signal(tests, "SIGTERM");
    await waitForExit(tests, testsTerminateGraceMs);
    signal(tests, "SIGKILL");
    await waitForExit(tests, killGraceMs);
    process.exitCode = 124;
  }, wrapperTimeout);
  await finished;
  clearTimeout(timeout);
};

try {
  await run();
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
} finally {
  signal(tests, "SIGTERM");
  signal(server, "SIGTERM");
  await waitForExit(tests, terminateGraceMs);
  await waitForExit(server, terminateGraceMs);
  signal(tests, "SIGKILL");
  signal(server, "SIGKILL");
  await waitForExit(tests, killGraceMs);
  await waitForExit(server, killGraceMs);
}
