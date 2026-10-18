import { defineConfig, devices } from "@playwright/test";

const webUrl = process.env.WEB_URL ?? "http://127.0.0.1:3101";
const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8100";
const e2eBrowser = process.env.E2E_BROWSER ?? "chromium";
const chromiumChannel =
  process.env.CI || process.env.PLAYWRIGHT_CHROMIUM_CHANNEL
    ? undefined
    : "chrome";

const chromiumDesktop = {
  ...devices["Desktop Chrome"],
  ...(chromiumChannel ? { channel: chromiumChannel } : {}),
};
const chromiumMobile = {
  ...devices["iPhone 13"],
  browserName: "chromium" as const,
  ...(chromiumChannel ? { channel: chromiumChannel } : {}),
};

const projectByBrowser = {
  chromium: [
    { name: "desktop-chromium", use: chromiumDesktop },
    { name: "mobile-chrome", use: chromiumMobile },
  ],
  webkit: [
    { name: "desktop-webkit-safari", use: { ...devices["Desktop Safari"] } },
    {
      name: "mobile-webkit-iphone13",
      use: { ...devices["iPhone 13"], browserName: "webkit" as const },
    },
  ],
};

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  globalTimeout: Number(process.env.PLAYWRIGHT_GLOBAL_TIMEOUT_MS ?? 15 * 60_000),
  workers: 1,
  retries: Number(process.env.PLAYWRIGHT_RETRIES ?? 0),
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: webUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: projectByBrowser[e2eBrowser as keyof typeof projectByBrowser],
  webServer: process.env.PLAYWRIGHT_EXTERNAL_SERVERS
    ? undefined
    : [
        {
          command: "uv run uvicorn app.main:app --host 127.0.0.1 --port 8100",
          cwd: "..",
          env: {
            APP_ENV: "development",
            COOKIE_SECURE: "false",
            AUTH_RATE_LIMIT_PER_MINUTE: "100",
            APP_ALLOWED_ORIGINS: JSON.stringify([webUrl]),
            CSRF_ALLOWED_ORIGINS: JSON.stringify([webUrl]),
            PASSWORD_RESET_BASE_URL: `${webUrl}/reset-password`,
            SMTP_HOST: "",
            MAIL_LOCAL_RESET_FILE:
              process.env.MAIL_LOCAL_RESET_FILE ??
              "/private/tmp/technical-interview-agent-password-reset.json",
            RESUME_STORAGE_DIR:
              process.env.RESUME_STORAGE_DIR ??
              "/private/tmp/technical-interview-agent-resume-files",
          },
          url: `${apiUrl}/health/live`,
          reuseExistingServer: false,
          timeout: 120_000,
        },
        {
          command: process.env.PLAYWRIGHT_WEB_COMMAND ?? "npm run dev -- --port 3101",
          env: {
            VITE_API_BASE_URL: apiUrl,
          },
          url: webUrl,
          reuseExistingServer: false,
          timeout: 120_000,
        },
      ],
});
