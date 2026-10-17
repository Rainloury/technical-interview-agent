import { readCsrfToken } from "./csrf";
import type {
  ApiErrorBody,
  Dashboard,
  HistoryPage,
  HistoryType,
  Interview,
  InterviewAccepted,
  InterviewBranchAction,
  InterviewCreated,
  InterviewDifficulty,
  InterviewDirection,
  InterviewReport,
  InterviewStart,
  LoginResponse,
  QaAccepted,
  QaAnswerPreference,
  QaRequest,
  QaStreamEvent,
  RegisterResponse,
  ResumeAccepted,
  ResumeTask,
  ReviewPage,
  Session,
  WeakPoint,
  WrongQuestionDetail,
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

export interface ParsedSseEvent {
  id?: string;
  type: string;
  data: string;
}

export interface QaStreamOptions {
  afterSeq?: number;
  lastEventId?: string;
  signal?: AbortSignal;
  maxReconnects?: number;
  reconnectDelayMs?: number;
  onEvent: (event: QaStreamEvent) => void;
  onReconnect?: (attempt: number) => void;
}

class SseParseError extends Error {
  constructor() {
    super("SSE event data was not a JSON object");
    this.name = "SseParseError";
  }
}

function dispatchSseEvent(
  eventType: string | null,
  eventId: string | null,
  dataLines: string[],
  onEvent: (event: ParsedSseEvent) => void,
): void {
  if (dataLines.length === 0) {
    return;
  }
  onEvent({
    ...(eventId ? { id: eventId } : {}),
    type: eventType || "message",
    data: dataLines.join("\n"),
  });
}

export async function parseSseStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: ParsedSseEvent) => void,
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventType: string | null = null;
  let eventId: string | null = null;
  let dataLines: string[] = [];

  const consumeLine = (rawLine: string) => {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (line === "") {
      dispatchSseEvent(eventType, eventId, dataLines, onEvent);
      eventType = null;
      eventId = null;
      dataLines = [];
      return;
    }
    if (line.startsWith(":")) {
      return;
    }
    const separator = line.indexOf(":");
    const field = separator < 0 ? line : line.slice(0, separator);
    let value = separator < 0 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }
    if (field === "event") {
      eventType = value;
    } else if (field === "id") {
      eventId = value;
    } else if (field === "data") {
      dataLines.push(value);
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let newline = buffer.indexOf("\n");
      while (newline >= 0) {
        consumeLine(buffer.slice(0, newline));
        buffer = buffer.slice(newline + 1);
        newline = buffer.indexOf("\n");
      }
    }
    buffer += decoder.decode();
    if (buffer) {
      consumeLine(buffer);
    }
    dispatchSseEvent(eventType, eventId, dataLines, onEvent);
  } finally {
    reader.releaseLock();
  }
}

function waitForReconnect(signal: AbortSignal | undefined, milliseconds: number) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("The operation was aborted.", "AbortError"));
      return;
    }
    const timeout = window.setTimeout(resolve, milliseconds);
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timeout);
        reject(new DOMException("The operation was aborted.", "AbortError"));
      },
      { once: true },
    );
  });
}

async function streamQa(id: string, options: QaStreamOptions): Promise<void> {
  const maximumReconnects = options.maxReconnects ?? 3;
  const reconnectDelayMs = options.reconnectDelayMs ?? 500;
  const seenEventIds = new Set<string>();
  let lastEventId = options.lastEventId;
  let reconnectAttempt = 0;
  let firstConnection = true;
  let makeProgress = false;

  while (true) {
    const headers = new Headers({ Accept: "text/event-stream" });
    if (lastEventId) {
      headers.set("Last-Event-ID", lastEventId);
    }
    const cursor =
      firstConnection && options.afterSeq !== undefined
        ? `?after_seq=${options.afterSeq}`
        : "";
    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}/api/v1/qa/${id}/stream${cursor}`, {
        method: "GET",
        headers,
        credentials: "include",
        signal: options.signal,
      });
    } catch {
      if (options.signal?.aborted) {
        return;
      }
      if (reconnectAttempt >= maximumReconnects) {
        throw new ApiError("回答连接中断，请稍后重试。", {
          status: 0,
          code: "stream_disconnected",
          retryable: true,
        });
      }
      reconnectAttempt += 1;
      options.onReconnect?.(reconnectAttempt);
      firstConnection = false;
      await waitForReconnect(options.signal, reconnectDelayMs);
      continue;
    }

    firstConnection = false;
    if (!response.ok) {
      const error = await parseError(response);
      if (error.status < 500 || reconnectAttempt >= maximumReconnects) {
        throw error;
      }
      reconnectAttempt += 1;
      options.onReconnect?.(reconnectAttempt);
      await waitForReconnect(options.signal, reconnectDelayMs);
      continue;
    }
    if (!response.body) {
      throw new ApiError("回答流不可用，请稍后重试。", {
        status: response.status,
        code: "stream_unavailable",
        retryable: true,
      });
    }

    let terminal = false;
    try {
      await parseSseStream(response.body, (parsed) => {
        makeProgress = true;
        if (parsed.id) {
          if (seenEventIds.has(parsed.id)) {
            return;
          }
          seenEventIds.add(parsed.id);
          lastEventId = parsed.id;
        }
        let parsedData: unknown;
        try {
          parsedData = JSON.parse(parsed.data);
        } catch {
          throw new SseParseError();
        }
        if (
          typeof parsedData !== "object" ||
          parsedData === null ||
          Array.isArray(parsedData) ||
          !["started", "delta", "evidence", "completed", "error"].includes(parsed.type)
        ) {
          throw new SseParseError();
        }
        const event: QaStreamEvent = {
          id: parsed.id ? Number(parsed.id) : 0,
          type: parsed.type as QaStreamEvent["type"],
          data: parsedData as QaStreamEvent["data"],
        };
        terminal = event.type === "completed" || event.type === "error";
        options.onEvent(event);
      });
    } catch (error) {
      if (options.signal?.aborted) {
        return;
      }
      if (error instanceof SseParseError) {
        throw new ApiError("回答流返回了无法识别的数据。", {
          status: response.status,
          code: "invalid_stream_event",
        });
      }
      if (reconnectAttempt >= maximumReconnects) {
        throw new ApiError("回答连接中断，请稍后重试。", {
          status: 0,
          code: "stream_disconnected",
          retryable: true,
        });
      }
    }

    if (terminal) {
      return;
    }
    if (reconnectAttempt >= maximumReconnects) {
      throw new ApiError("回答连接中断，请稍后重试。", {
        status: 0,
        code: "stream_disconnected",
        retryable: true,
      });
    }
    if (!makeProgress) {
      throw new ApiError("回答连接中断，请稍后重试。", {
        status: 0,
        code: "stream_disconnected",
        retryable: true,
      });
    }
    reconnectAttempt += 1;
    makeProgress = false;
    options.onReconnect?.(reconnectAttempt);
    await waitForReconnect(options.signal, reconnectDelayMs);
  }
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
  createQa: (
    question: string,
    answerPreference: QaAnswerPreference,
    idempotencyKey: string,
  ) =>
    request<QaAccepted>("/api/v1/qa", {
      method: "POST",
      body: {
        question,
        answer_preference: answerPreference,
      },
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  qa: (id: string) => request<QaRequest>(`/api/v1/qa/${id}`),
  streamQa,
  createInterview: (
    direction: InterviewDirection,
    difficulty: InterviewDifficulty,
    topicKeys: string[],
    idempotencyKey: string,
  ) =>
    request<InterviewCreated>("/api/v1/interviews", {
      method: "POST",
      body: { direction, difficulty, topic_keys: topicKeys },
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  startInterview: (id: string, idempotencyKey: string) =>
    request<InterviewStart>(`/api/v1/interviews/${id}/start`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  interview: (id: string) => request<Interview>(`/api/v1/interviews/${id}`),
  answerInterview: (
    id: string,
    turnId: string,
    answer: string,
    idempotencyKey: string,
  ) =>
    request<InterviewAccepted>(
      `/api/v1/interviews/${id}/turns/${turnId}/answer`,
      {
        method: "POST",
        body: {
          answer,
          client_submitted_at: new Date().toISOString(),
        },
        headers: { "Idempotency-Key": idempotencyKey },
      },
    ),
  skipInterviewTurn: (id: string, turnId: string, key: string) =>
    request<InterviewBranchAction>(
      `/api/v1/interviews/${id}/turns/${turnId}/skip`,
      { method: "POST", headers: { "Idempotency-Key": key } },
    ),
  endInterviewBranch: (id: string, turnId: string, key: string) =>
    request<InterviewBranchAction>(
      `/api/v1/interviews/${id}/turns/${turnId}/end-branch`,
      { method: "POST", headers: { "Idempotency-Key": key } },
    ),
  interviewReport: (id: string) =>
    request<InterviewReport>(`/api/v1/interviews/${id}/report`),
  wrongQuestions: (cursor?: string | null, limit = 20) =>
    request<ReviewPage<WrongQuestionDetail>>("/api/v1/wrong-questions", {
      query: { cursor, limit },
    }),
  wrongQuestion: (id: string) =>
    request<WrongQuestionDetail>(`/api/v1/wrong-questions/${id}`),
  weakPoints: (cursor?: string | null, limit = 20) =>
    request<ReviewPage<WeakPoint>>("/api/v1/weak-points", {
      query: { cursor, limit },
    }),
};
