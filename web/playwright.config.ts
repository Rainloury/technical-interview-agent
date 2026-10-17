import { defineConfig, devices } from "@playwright/test";

const webUrl = process.env.WEB_URL ?? "http://127.0.0.1:3101";
const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8100";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: webUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
    {
      name: "mobile-chrome",
      use: { ...devices["iPhone 13"], browserName: "chromium", channel: "chrome" },
    },
  ],
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
          },
          url: `${apiUrl}/health/live`,
          reuseExistingServer: false,
          timeout: 120_000,
        },
        {
          command: "npm run dev -- --port 3101",
          env: {
            VITE_API_BASE_URL: apiUrl,
          },
          url: webUrl,
          reuseExistingServer: false,
          timeout: 120_000,
        },
      ],
});
