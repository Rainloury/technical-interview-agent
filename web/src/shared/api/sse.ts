import { API_BASE_URL, ApiError, parseError } from "@/shared/api/http";
import type { QaStreamEvent } from "@/shared/api/types";

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

export async function streamQa(id: string, options: QaStreamOptions): Promise<void> {
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
        // parsed.type 来自 SSE 的 event: 字段（后端固定输出业务事件类型），
        // payload 本身不含 type，因此事件类型校验必须针对 parsed.type。
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
          retryable: false,
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
