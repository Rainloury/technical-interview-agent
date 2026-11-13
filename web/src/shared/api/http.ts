import { readCsrfToken } from "@/shared/api/csrf";
import type { ApiErrorBody } from "@/shared/api/types";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const defaultBaseUrl = import.meta.env.DEV ? "http://127.0.0.1:8000" : "";
export const API_BASE_URL = (configuredBaseUrl || defaultBaseUrl).replace(/\/$/, "");

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

export const REQUEST_TIMEOUT_MS = 15_000;

interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  body?: unknown;
  formData?: FormData;
  query?: Record<string, string | number | null | undefined>;
  headers?: Record<string, string>;
  signal?: AbortSignal;
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

export async function parseError(response: Response): Promise<ApiError> {
  let payload: ApiErrorBody = {};
  try {
    payload = (await response.json()) as ApiErrorBody;
  } catch {
    // 代理或故障可能返回非 JSON 响应体。
  }
  return new ApiError(payload.error?.message || "请求未完成，请稍后重试。", {
    status: response.status,
    code: payload.error?.code || "request_failed",
    retryable: payload.error?.retryable,
    requestId: payload.error?.request_id,
  });
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
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

  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);
  const forwardAbort = () => controller.abort();
  options.signal?.addEventListener("abort", forwardAbort, { once: true });

  try {
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
        signal: controller.signal,
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
  } catch (error) {
    if (timedOut) {
      throw new ApiError("请求超时，请稍后重试。", {
        status: 0,
        code: "request_timeout",
        retryable: true,
      });
    }
    if (error instanceof ApiError) {
      throw error;
    }
    if (options.signal?.aborted) {
      throw new ApiError("请求已取消。", {
        status: 0,
        code: "request_aborted",
        retryable: false,
      });
    }
    throw new ApiError("请求未完成，请稍后重试。", {
      status: 0,
      code: "request_failed",
    });
  } finally {
    clearTimeout(timeoutId);
    options.signal?.removeEventListener("abort", forwardAbort);
  }
}
