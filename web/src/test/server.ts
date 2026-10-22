import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import type { Dashboard, HistoryPage, Session } from "../api/types";

export const demoSession: Session = {
  user: { id: "user-1", display_name: "示例用户", role: "user" },
  session: { expires_at: "2026-10-24T08:30:00Z" },
};

export const demoDashboard: Dashboard = {
  user: demoSession.user,
  recent_tasks: [
    {
      id: "task-1",
      type: "resume",
      title: "后端简历.pdf",
      state: "completed",
      updated_at: "2026-10-17T08:00:00Z",
    },
    {
      id: "task-2",
      type: "qa",
      title: "如何解释数据库索引？",
      state: "completed",
      updated_at: "2026-10-17T07:00:00Z",
    },
  ],
  recent_interviews: [
    {
      id: "interview-1",
      direction: "backend",
      state: "ended",
      updated_at: "2026-10-17T06:00:00Z",
    },
  ],
  server_time: "2026-10-17T08:30:00Z",
};

export const emptyDashboard: Dashboard = {
  user: demoSession.user,
  recent_tasks: [],
  recent_interviews: [],
  server_time: "2026-10-17T08:30:00Z",
};

export const demoHistory: HistoryPage = {
  items: [
    {
      id: "interview-1",
      type: "interview",
      title: "后端方向模拟面试",
      state: "ended",
      updated_at: "2026-10-17T06:00:00Z",
    },
  ],
  next_cursor: null,
};

export const emptyHistory: HistoryPage = { items: [], next_cursor: null };

export const handlers = [
  http.get("*/api/v1/auth/session", () =>
    HttpResponse.json(
      {
        error: {
          code: "authentication_required",
          message: "请先登录",
          retryable: false,
        },
      },
      { status: 401 },
    ),
  ),
  http.post("*/api/v1/auth/login", () =>
    HttpResponse.json(
      { user: demoSession.user, session: demoSession.session },
      {
        headers: {
          "Set-Cookie": "interview_csrf=test-csrf; Path=/; SameSite=Lax",
        },
      },
    ),
  ),
  http.post("*/api/v1/auth/register", () =>
    HttpResponse.json(
      { accepted: true, next_action: "login" },
      { status: 202 },
    ),
  ),
  http.post("*/api/v1/auth/logout", () => new HttpResponse(null, { status: 204 })),
  http.post("*/api/v1/auth/password-reset/request", () =>
    HttpResponse.json({ accepted: true }, { status: 202 }),
  ),
  http.post("*/api/v1/auth/password-reset/confirm", () =>
    new HttpResponse(null, { status: 204 }),
  ),
  http.get("*/api/v1/dashboard", () => HttpResponse.json(demoDashboard)),
  http.get("*/api/v1/history", ({ request }) => {
    const type = new URL(request.url).searchParams.get("type");
    if (type === "interview") {
      return HttpResponse.json(demoHistory);
    }
    return HttpResponse.json(emptyHistory);
  }),
];

export const server = setupServer(...handlers);

export function authenticatedSessionHandler() {
  return http.get("*/api/v1/auth/session", () => HttpResponse.json(demoSession));
}

export function loginFlowHandlers() {
  let authenticated = false;

  return [
    http.get("*/api/v1/auth/session", () => {
      if (authenticated) {
        return HttpResponse.json(demoSession);
      }
      return HttpResponse.json(
        {
          error: {
            code: "authentication_required",
            message: "请先登录",
            retryable: false,
          },
        },
        { status: 401 },
      );
    }),
    http.post("*/api/v1/auth/login", () => {
      authenticated = true;
      return HttpResponse.json(
        { user: demoSession.user, session: demoSession.session },
        {
          headers: {
            "Set-Cookie": "interview_csrf=test-csrf; Path=/; SameSite=Lax",
          },
        },
      );
    }),
  ];
}
