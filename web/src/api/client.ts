import { readCsrfToken } from "./csrf";
import type {
  ApiErrorBody,
  Dashboard,
  HistoryPage,
  HistoryType,
  LoginResponse,
  RegisterResponse,
  ResumeAccepted,
  ResumeTask,
  Session,
} from "./types";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const API_BASE_URL = (configuredBaseUrl || "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly requestId?: string;

  constructor(
    message: string,
    options: {
      status: number;
      code: string;
      retryable?: boolean;
      requestId?: string;
    },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.retryable = options.retryable ?? false;
    this.requestId = options.requestId;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  body?: unknown;
  formData?: FormData;
  query?: Record<string, string | number | null | undefined>;
  headers?: Record<string, string>;
}

function queryString(query: RequestOptions["query"]): string {
  if (!query) {
    return "";
  }
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  }
  const result = params.toString();
  return result ? `?${result}` : "";
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: ApiErrorBody = {};
  try {
    payload = (await response.json()) as ApiErrorBody;
  } catch {
    // A proxy or outage can return a non-JSON body.
  }
  return new ApiError(payload.error?.message || "请求未完成，请稍后重试。", {
    status: response.status,
    code: payload.error?.code || "request_failed",
    retryable: payload.error?.retryable,
    requestId: payload.error?.request_id,
  });
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers = new Headers({ Accept: "application/json" });
  if (options.body !== undefined && options.formData !== undefined) {
    throw new Error("request body and formData are mutually exclusive");
  }
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  for (const [name, value] of Object.entries(options.headers ?? {})) {
    headers.set(name, value);
  }
  if (method !== "GET") {
    const csrfToken = readCsrfToken();
    if (csrfToken) {
      headers.set("X-CSRF-Token", csrfToken);
    }
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}${queryString(options.query)}`, {
      method,
      headers,
      credentials: "include",
      body:
        options.formData !== undefined
          ? options.formData
          : options.body === undefined
            ? undefined
            : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError("无法连接服务，请检查网络后重试。", {
      status: 0,
      code: "network_error",
      retryable: true,
    });
  }

  if (!response.ok) {
    throw await parseError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  session: () => request<Session>("/api/v1/auth/session"),
  login: (email: string, password: string) =>
    request<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
    }),
  register: (email: string, password: string) =>
    request<RegisterResponse>("/api/v1/auth/register", {
      method: "POST",
      body: { email, password },
    }),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  requestPasswordReset: (email: string) =>
    request<{ accepted: true }>("/api/v1/auth/password-reset/request", {
      method: "POST",
      body: { email },
    }),
  confirmPasswordReset: (token: string, newPassword: string) =>
    request<void>("/api/v1/auth/password-reset/confirm", {
      method: "POST",
      body: { token, new_password: newPassword },
    }),
  dashboard: () => request<Dashboard>("/api/v1/dashboard"),
  history: (type: HistoryType, cursor?: string | null, limit = 10) =>
    request<HistoryPage>("/api/v1/history", {
      query: { type, limit, cursor },
    }),
  resume: (id: string) => request<ResumeTask>(`/api/v1/resumes/${id}`),
  uploadResume: (
    file: File,
    targetRole: string,
    idempotencyKey: string,
  ) => {
    const formData = new FormData();
    formData.set("file", file);
    if (targetRole.trim()) {
      formData.set("target_role", targetRole.trim());
    }
    return request<ResumeAccepted>("/api/v1/resumes", {
      method: "POST",
      formData,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
  retryResume: (id: string, idempotencyKey: string) =>
    request<ResumeAccepted>(`/api/v1/resumes/${id}/retry`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  deleteResumeSource: (id: string, idempotencyKey: string) =>
    request<void>(`/api/v1/resumes/${id}/source`, {
      method: "DELETE",
      headers: { "Idempotency-Key": idempotencyKey },
    }),
};
