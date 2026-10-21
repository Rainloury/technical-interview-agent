import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { authenticatedSessionHandler, server } from "../test/server";
import { renderApp } from "../test/render";
import type { DocumentItem } from "../api/types";
import { validateDocument } from "../utils/documentValidation";

const READY_DOCUMENT: DocumentItem = {
  id: "document-1",
  title: "Redis 设计笔记",
  original_filename: "redis.md",
  state: "ready",
  chunk_count: 8,
  failure_code: null,
  error_message: null,
  index_version: "rag-v1",
  created_at: "2026-10-21T08:00:00Z",
  updated_at: "2026-10-21T08:01:00Z",
  completed_at: "2026-10-21T08:01:00Z",
  retention_expires_at: "2027-01-19T08:01:00Z",
};

function documentsHandler(items = [READY_DOCUMENT]) {
  return http.get("*/api/v1/documents", () =>
    HttpResponse.json({ items, next_cursor: null }),
  );
}

describe("DocumentsPage", () => {
  it("validates document format and size before upload", () => {
    expect(validateDocument(null)).toBe("请选择资料文件。");
    expect(validateDocument(new File(["x"], "notes.exe", { type: "text/plain" }))).toBe(
      "仅支持 PDF、DOCX、TXT 或 Markdown 文件。",
    );
    expect(
      validateDocument(
        new File([new Uint8Array(10 * 1024 * 1024 + 1)], "large.md", {
          type: "text/markdown",
        }),
      ),
    ).toBe("文件不能超过 10 MB。");
  });

  it("lists private documents and supports empty state", async () => {
    server.use(authenticatedSessionHandler(), documentsHandler([]));
    renderApp("/documents");

    expect(await screen.findByText("还没有内部资料")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "上传第一份资料" })).toBeInTheDocument();
  });

  it("uploads a document with csrf and idempotency key", async () => {
    const user = userEvent.setup();
    const observed: {
      csrf: string | null;
      key: string | null;
      contentType: string | null;
    }[] = [];
    let items = [READY_DOCUMENT];
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/documents", () => HttpResponse.json({ items, next_cursor: null })),
      http.post("*/api/v1/documents", async ({ request }) => {
        observed.push({
          csrf: request.headers.get("X-CSRF-Token"),
          key: request.headers.get("Idempotency-Key"),
          contentType: request.headers.get("Content-Type"),
        });
        items = [
          {
            ...READY_DOCUMENT,
            id: "document-2",
            title: "新资料",
            original_filename: "notes.txt",
          },
        ];
        return HttpResponse.json(
          {
            document_id: "document-2",
            state: "uploaded",
            created_at: "2026-10-21T09:00:00Z",
          },
          { status: 202 },
        );
      }),
    );
    document.cookie = "interview_csrf=documents-csrf; path=/";
    renderApp("/documents");

    const file = new File(["Redis"], "notes.txt", { type: "text/plain" });
    await user.upload(await screen.findByLabelText("资料文件"), file);
    await user.type(screen.getByLabelText("资料标题"), "新资料");
    await user.click(screen.getByRole("button", { name: "上传资料" }));

    await waitFor(() => expect(observed).toHaveLength(1));
    expect(observed[0]?.csrf).toBe("documents-csrf");
    expect(observed[0]?.key).toBeTruthy();
    expect(observed[0]?.contentType).toMatch(/^multipart\/form-data; boundary=/);
  });

  it("shows document states and upload failures with retry", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    server.use(
      authenticatedSessionHandler(),
      documentsHandler([
        READY_DOCUMENT,
        { ...READY_DOCUMENT, id: "document-processing", title: "处理中", state: "processing" },
        { ...READY_DOCUMENT, id: "document-failed", title: "失败资料", state: "failed", failure_code: "embedding_timeout" },
      ]),
      http.post("*/api/v1/documents", () => {
        attempts += 1;
        if (attempts === 1) {
          return HttpResponse.json(
            { error: { code: "embedding_unavailable", message: "上传暂时失败", retryable: true } },
            { status: 503 },
          );
        }
        return HttpResponse.json(
          { document_id: "document-3", state: "uploaded", created_at: "2026-10-21T09:00:00Z" },
          { status: 202 },
        );
      }),
    );
    renderApp("/documents");

    expect(await screen.findByText("可检索")).toBeInTheDocument();
    expect(screen.getAllByText("处理中")).toHaveLength(2);
    expect(screen.getByText("索引失败")).toBeInTheDocument();
    const file = new File(["Retry"], "retry.txt", { type: "text/plain" });
    await user.upload(screen.getByLabelText("资料文件"), file);
    await user.click(screen.getByRole("button", { name: "上传资料" }));
    expect(await screen.findByText("上传暂时失败")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => expect(attempts).toBe(2));
  });

  it("deletes a document after confirmation with csrf", async () => {
    const user = userEvent.setup();
    let items = [READY_DOCUMENT];
    let deleteHeaders: Headers | null = null;
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/documents", () => HttpResponse.json({ items, next_cursor: null })),
      http.delete("*/api/v1/documents/document-1", ({ request }) => {
        deleteHeaders = request.headers;
        items = [];
        return new HttpResponse(null, { status: 204 });
      }),
    );
    document.cookie = "interview_csrf=delete-csrf; path=/";
    renderApp("/documents");

    expect(await screen.findByText("Redis 设计笔记")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "删除 Redis 设计笔记" }));
    await user.click(screen.getByRole("button", { name: "确认删除" }));

    await waitFor(() => expect(deleteHeaders?.get("X-CSRF-Token")).toBe("delete-csrf"));
    await waitFor(() => expect(screen.queryByText("Redis 设计笔记")).not.toBeInTheDocument());
  });
});
