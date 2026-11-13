import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { authenticatedSessionHandler, server } from "@/test/server";
import { renderApp } from "@/test/render";
import type { DocumentItem } from "@/shared/api/types";
import { validateDocument, validateDocuments } from "@/shared/lib/validation";

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
  visibility: "private",
  can_delete: true,
};

function documentsHandler(items = [READY_DOCUMENT]) {
  return http.get("*/api/v1/documents", () =>
    HttpResponse.json({ items, next_cursor: null }),
  );
}

const SHARED_DOCUMENT: DocumentItem = {
  ...READY_DOCUMENT,
  id: "shared-document-1",
  title: "共享重试手册",
  original_filename: "shared.md",
  visibility: "shared",
  can_delete: false,
};

function sharedDocumentsHandler(items = [SHARED_DOCUMENT]) {
  return http.get("*/api/v1/shared-documents", () =>
    HttpResponse.json({ items, next_cursor: null }),
  );
}

describe("DocumentsPage", () => {
  const adminSessionHandler = () =>
    http.get("*/api/v1/auth/session", () =>
      HttpResponse.json({
        user: { id: "admin-1", display_name: "管理员", role: "admin" },
        session: { expires_at: "2026-10-24T08:30:00Z" },
      }),
    );

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
    expect(validateDocuments([])).toBe("请选择资料文件。");
    expect(
      validateDocuments([
        new File(["ok"], "ok.md", { type: "text/markdown" }),
        new File(["x"], "bad.exe", { type: "application/octet-stream" }),
      ]),
    ).toContain("bad.exe");
  });

  it("lists private documents and supports empty state", async () => {
    server.use(authenticatedSessionHandler(), documentsHandler([]), sharedDocumentsHandler([]));
    renderApp("/documents");

    expect(await screen.findByText("还没有内部资料")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "上传第一份资料" })).toBeInTheDocument();
  });

  it("uploads multiple documents in one batch with csrf and idempotency key", async () => {
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
      http.post("*/api/v1/documents/batch", async ({ request }) => {
        observed.push({
          csrf: request.headers.get("X-CSRF-Token"),
          key: request.headers.get("Idempotency-Key"),
          contentType: request.headers.get("Content-Type"),
        });
        const form = await request.formData();
        expect(form.getAll("files")).toHaveLength(2);
        items = [
          { ...READY_DOCUMENT, id: "document-2", title: "notes.txt" },
          { ...READY_DOCUMENT, id: "document-3", title: "retry.md" },
        ];
        return HttpResponse.json(
          {
            documents: [
              {
                document_id: "document-2",
                state: "uploaded",
                created_at: "2026-10-21T09:00:00Z",
              },
              {
                document_id: "document-3",
                state: "uploaded",
                created_at: "2026-10-21T09:00:00Z",
              },
            ],
            original_filenames: ["notes.txt", "retry.md"],
          },
          { status: 202 },
        );
      }),
    );
    document.cookie = "interview_csrf=documents-csrf; path=/";
    renderApp("/documents");

    const files = [
      new File(["Redis"], "notes.txt", { type: "text/plain" }),
      new File(["Retry"], "retry.md", { type: "text/markdown" }),
    ];
    await user.upload(await screen.findByLabelText("资料文件"), files);
    await user.click(screen.getByRole("button", { name: "上传 2 个文件" }));

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
      sharedDocumentsHandler([]),
      http.post("*/api/v1/documents/batch", () => {
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
    await user.click(screen.getByRole("button", { name: "上传 1 个文件" }));
    expect(await screen.findByText("上传暂时失败")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => expect(attempts).toBe(2));
  });

  it("shows the stable failure code for a failed document", async () => {
    server.use(
      authenticatedSessionHandler(),
      documentsHandler([
        {
          ...READY_DOCUMENT,
          id: "document-failed",
          title: "失败资料",
          state: "failed",
          failure_code: "embedding_timeout",
          error_message: "资料索引未完成，请重新上传",
        },
      ]),
      sharedDocumentsHandler([]),
    );
    renderApp("/documents");

    expect(await screen.findByText("索引失败")).toBeInTheDocument();
    expect(screen.getByText(/embedding_timeout/)).toBeInTheDocument();
    expect(screen.queryByText("资料索引未完成，请重新上传")).not.toBeInTheDocument();
  });

  it("deletes a document after confirmation with csrf", async () => {
    const user = userEvent.setup();
    let items = [READY_DOCUMENT];
    let deleteHeaders: Headers | null = null;
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/documents", () => HttpResponse.json({ items, next_cursor: null })),
      sharedDocumentsHandler([]),
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

  it("selects all loaded private documents and toggles the selection off", async () => {
    const user = userEvent.setup();
    server.use(
      authenticatedSessionHandler(),
      documentsHandler([
        READY_DOCUMENT,
        { ...READY_DOCUMENT, id: "document-2", title: "重试手册" },
        { ...READY_DOCUMENT, id: "document-3", title: "索引手册" },
      ]),
      sharedDocumentsHandler([]),
    );
    renderApp("/documents");

    expect(await screen.findByText("Redis 设计笔记")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "删除已选 0 份" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "全选本页" }));

    expect(screen.getByText("已选 3 份")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "删除已选 3 份" })).toBeEnabled();
    expect(screen.getByRole("checkbox", { name: "选择 Redis 设计笔记" })).toBeChecked();

    await user.click(screen.getByRole("checkbox", { name: "全选本页" }));

    expect(screen.getByText("已选 0 份")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "删除已选 0 份" })).toBeDisabled();
  });

  it("bulk deletes only selected private documents with independent idempotency keys", async () => {
    const user = userEvent.setup();
    const deleted: { id: string | undefined; key: string | null; csrf: string | null }[] = [];
    let items = [
      READY_DOCUMENT,
      { ...READY_DOCUMENT, id: "document-2", title: "重试手册" },
      { ...READY_DOCUMENT, id: "document-3", title: "索引手册" },
    ];
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/documents", () => HttpResponse.json({ items, next_cursor: null })),
      sharedDocumentsHandler([]),
      http.delete("*/api/v1/documents/:id", ({ request, params }) => {
        const id = String(params.id);
        deleted.push({
          id,
          key: request.headers.get("Idempotency-Key"),
          csrf: request.headers.get("X-CSRF-Token"),
        });
        items = items.filter((item) => item.id !== id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    document.cookie = "interview_csrf=bulk-delete-csrf; path=/";
    renderApp("/documents");

    expect(await screen.findByText("Redis 设计笔记")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "选择 Redis 设计笔记" }));
    await user.click(screen.getByRole("checkbox", { name: "选择 索引手册" }));
    await user.click(screen.getByRole("button", { name: "删除已选 2 份" }));

    expect(screen.getByRole("heading", { name: "删除已选 2 份资料？" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认删除" }));

    await waitFor(() => expect(deleted).toHaveLength(2));
    expect(deleted.map((entry) => entry.id).sort()).toEqual(["document-1", "document-3"]);
    expect(new Set(deleted.map((entry) => entry.key)).size).toBe(2);
    expect(deleted.every((entry) => entry.key && entry.csrf === "bulk-delete-csrf")).toBe(true);
    await waitFor(() => {
      expect(screen.queryByText("Redis 设计笔记")).not.toBeInTheDocument();
      expect(screen.queryByText("索引手册")).not.toBeInTheDocument();
    });
    expect(screen.getByText("重试手册")).toBeInTheDocument();
  });

  it("selects only loaded documents when more pages are available", async () => {
    const user = userEvent.setup();
    let requests = 0;
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/documents", () => {
        requests += 1;
        if (requests === 1) {
          return HttpResponse.json({
            items: [
              READY_DOCUMENT,
              { ...READY_DOCUMENT, id: "document-2", title: "重试手册" },
            ],
            next_cursor: "next-page",
          });
        }
        return HttpResponse.json({
          items: [{ ...READY_DOCUMENT, id: "document-3", title: "索引手册" }],
          next_cursor: null,
        });
      }),
      sharedDocumentsHandler([]),
    );
    renderApp("/documents");

    expect(await screen.findByText("Redis 设计笔记")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "全选本页" }));
    expect(screen.getByText("已选 2 份")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "删除已选 2 份" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "加载更多" }));
    expect(await screen.findByText("索引手册")).toBeInTheDocument();
    expect(screen.getByText("已选 2 份")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "选择 索引手册" })).not.toBeChecked();
    await user.click(screen.getByRole("checkbox", { name: "全选本页" }));
    expect(screen.getByText("已选 3 份")).toBeInTheDocument();
  });

  it("keeps failed documents selected after a partial bulk delete", async () => {
    const user = userEvent.setup();
    let items = [
      READY_DOCUMENT,
      { ...READY_DOCUMENT, id: "document-2", title: "重试手册" },
    ];
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/documents", () => HttpResponse.json({ items, next_cursor: null })),
      sharedDocumentsHandler([]),
      http.delete("*/api/v1/documents/:id", ({ params }) => {
        const id = String(params.id);
        if (id === "document-2") {
          return HttpResponse.json(
            { error: { code: "request_failed", message: "删除失败", retryable: true } },
            { status: 503 },
          );
        }
        items = items.filter((item) => item.id !== id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderApp("/documents");

    expect(await screen.findByText("Redis 设计笔记")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "全选本页" }));
    await user.click(screen.getByRole("button", { name: "删除已选 2 份" }));
    await user.click(screen.getByRole("button", { name: "确认删除" }));

    expect(await screen.findByText("有 1 份资料删除失败，请重试。")).toBeInTheDocument();
    expect(screen.queryByText("Redis 设计笔记")).not.toBeInTheDocument();
    expect(screen.getByText("重试手册")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "选择 重试手册" })).toBeChecked();
    expect(screen.getByText("已选 1 份")).toBeInTheDocument();
  });

  it("shows shared documents to regular users without write controls", async () => {
    server.use(
      authenticatedSessionHandler(),
      documentsHandler([]),
      sharedDocumentsHandler(),
    );
    renderApp("/documents");

    expect(await screen.findByText("共享重试手册")).toBeInTheDocument();
    expect(screen.queryByLabelText("共享资料文件")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "删除 共享重试手册" })).not.toBeInTheDocument();
  });

  it("does not show shared document selection controls to regular users", async () => {
    server.use(
      authenticatedSessionHandler(),
      documentsHandler([]),
      sharedDocumentsHandler([
        SHARED_DOCUMENT,
        { ...SHARED_DOCUMENT, id: "shared-document-2", title: "共享索引手册" },
      ]),
    );
    renderApp("/documents");

    expect(await screen.findByText("共享重试手册")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "全选共享资料" })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "选择 共享重试手册" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /删除已选共享/ })).not.toBeInTheDocument();
  });

  it("lets administrators bulk delete selected shared documents with independent keys", async () => {
    const user = userEvent.setup();
    const deleted: { id: string | undefined; key: string | null; csrf: string | null }[] = [];
    let sharedItems = [
      SHARED_DOCUMENT,
      { ...SHARED_DOCUMENT, id: "shared-document-2", title: "共享索引手册" },
      { ...SHARED_DOCUMENT, id: "shared-document-3", title: "共享缓存手册" },
    ];
    server.use(
      adminSessionHandler(),
      documentsHandler([]),
      http.get("*/api/v1/shared-documents", () =>
        HttpResponse.json({ items: sharedItems, next_cursor: null }),
      ),
      http.delete("*/api/v1/shared-documents/:id", ({ request, params }) => {
        const id = String(params.id);
        deleted.push({
          id,
          key: request.headers.get("Idempotency-Key"),
          csrf: request.headers.get("X-CSRF-Token"),
        });
        sharedItems = sharedItems.filter((item) => item.id !== id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    document.cookie = "interview_csrf=shared-bulk-delete-csrf; path=/";
    renderApp("/documents");

    expect(await screen.findByText("共享重试手册")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "选择 共享重试手册" }));
    await user.click(screen.getByRole("checkbox", { name: "选择 共享缓存手册" }));
    await user.click(screen.getByRole("button", { name: "删除已选共享 2 份" }));

    expect(
      screen.getByRole("heading", { name: "删除已选 2 份共享资料？" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认删除" }));

    await waitFor(() => expect(deleted).toHaveLength(2));
    expect(deleted.map((entry) => entry.id).sort()).toEqual([
      "shared-document-1",
      "shared-document-3",
    ]);
    expect(new Set(deleted.map((entry) => entry.key)).size).toBe(2);
    expect(
      deleted.every((entry) => entry.key && entry.csrf === "shared-bulk-delete-csrf"),
    ).toBe(true);
    await waitFor(() => {
      expect(screen.queryByText("共享重试手册")).not.toBeInTheDocument();
      expect(screen.queryByText("共享缓存手册")).not.toBeInTheDocument();
    });
    expect(screen.getByText("共享索引手册")).toBeInTheDocument();
  });

  it("keeps failed shared documents selected after a partial bulk delete", async () => {
    const user = userEvent.setup();
    let sharedItems = [
      SHARED_DOCUMENT,
      { ...SHARED_DOCUMENT, id: "shared-document-2", title: "共享索引手册" },
    ];
    server.use(
      adminSessionHandler(),
      documentsHandler([]),
      http.get("*/api/v1/shared-documents", () =>
        HttpResponse.json({ items: sharedItems, next_cursor: null }),
      ),
      http.delete("*/api/v1/shared-documents/:id", ({ params }) => {
        const id = String(params.id);
        if (id === "shared-document-2") {
          return HttpResponse.json(
            { error: { code: "request_failed", message: "删除失败", retryable: true } },
            { status: 503 },
          );
        }
        sharedItems = sharedItems.filter((item) => item.id !== id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderApp("/documents");

    expect(await screen.findByText("共享重试手册")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "全选共享资料" }));
    await user.click(screen.getByRole("button", { name: "删除已选共享 2 份" }));
    await user.click(screen.getByRole("button", { name: "确认删除" }));

    expect(await screen.findByText("有 1 份共享资料删除失败，请重试。")).toBeInTheDocument();
    expect(screen.queryByText("共享重试手册")).not.toBeInTheDocument();
    expect(screen.getByText("共享索引手册")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "选择 共享索引手册" })).toBeChecked();
    expect(screen.getByRole("button", { name: "删除已选共享 1 份" })).toBeEnabled();
  });

  it("keeps private and shared bulk selections independent", async () => {
    const user = userEvent.setup();
    server.use(
      adminSessionHandler(),
      documentsHandler([
        READY_DOCUMENT,
        { ...READY_DOCUMENT, id: "document-2", title: "重试手册" },
      ]),
      sharedDocumentsHandler([
        SHARED_DOCUMENT,
        { ...SHARED_DOCUMENT, id: "shared-document-2", title: "共享索引手册" },
        { ...SHARED_DOCUMENT, id: "shared-document-3", title: "共享缓存手册" },
      ]),
    );
    renderApp("/documents");

    expect(await screen.findByText("Redis 设计笔记")).toBeInTheDocument();
    const allCheckboxes = screen.getAllByRole("checkbox", { name: "全选本页" });
    expect(allCheckboxes).toHaveLength(1);
    await user.click(screen.getByRole("checkbox", { name: "选择 Redis 设计笔记" }));
    await user.click(screen.getByRole("checkbox", { name: "全选共享资料" }));

    expect(screen.getByRole("button", { name: "删除已选 1 份" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "删除已选共享 3 份" })).toBeEnabled();
    expect(screen.getByRole("checkbox", { name: "选择 重试手册" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "选择 共享缓存手册" })).toBeChecked();
  });

  it("lets administrators upload and delete shared documents", async () => {
    const user = userEvent.setup();
    const observed: { path: string; key: string | null }[] = [];
    let sharedItems = [SHARED_DOCUMENT];
    server.use(
      http.get("*/api/v1/auth/session", () =>
        HttpResponse.json({
          user: { id: "admin-1", display_name: "管理员", role: "admin" },
          session: { expires_at: "2026-10-24T08:30:00Z" },
        }),
      ),
      documentsHandler([]),
      http.get("*/api/v1/shared-documents", () =>
        HttpResponse.json({ items: sharedItems, next_cursor: null }),
      ),
      http.post("*/api/v1/shared-documents/batch", ({ request }) => {
        observed.push({
          path: new URL(request.url).pathname,
          key: request.headers.get("Idempotency-Key"),
        });
        sharedItems = [{ ...SHARED_DOCUMENT, id: "shared-document-2", title: "新共享资料" }];
        return HttpResponse.json(
          {
            documents: [
              {
                document_id: "shared-document-2",
                state: "uploaded",
                created_at: "2026-10-21T09:00:00Z",
              },
            ],
            original_filenames: ["new-shared.md"],
          },
          { status: 202 },
        );
      }),
      http.delete("*/api/v1/shared-documents/*", () => {
        sharedItems = [];
        return new HttpResponse(null, { status: 204 });
      }),
    );
    document.cookie = "interview_csrf=shared-csrf; path=/";
    renderApp("/documents");

    const file = new File(["Shared"], "new-shared.md", { type: "text/markdown" });
    await user.upload(await screen.findByLabelText("共享资料文件"), file);
    await user.click(screen.getByRole("button", { name: "上传 1 个共享文件" }));
    await waitFor(() => expect(observed).toHaveLength(1));
    expect(observed[0]?.path).toBe("/api/v1/shared-documents/batch");
    expect(observed[0]?.key).toBeTruthy();

    await user.click(await screen.findByRole("button", { name: "删除 新共享资料" }));
    await user.click(screen.getByRole("button", { name: "确认删除" }));
    await waitFor(() =>
      expect(screen.queryByText("新共享资料")).not.toBeInTheDocument(),
    );
  });

  it("shows a shared upload permission error without adding an optimistic row", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("*/api/v1/auth/session", () =>
        HttpResponse.json({
          user: { id: "admin-2", display_name: "管理员", role: "admin" },
          session: { expires_at: "2026-10-24T08:30:00Z" },
        }),
      ),
      documentsHandler([]),
      sharedDocumentsHandler([]),
      http.post("*/api/v1/shared-documents/batch", () =>
        HttpResponse.json(
          {
            error: {
              code: "admin_required",
              message: "当前账号没有共享资料权限",
              retryable: false,
            },
          },
          { status: 403 },
        ),
      ),
    );
    document.cookie = "interview_csrf=shared-error-csrf; path=/";
    renderApp("/documents");

    await user.upload(
      await screen.findByLabelText("共享资料文件"),
      new File(["Shared"], "denied.md", { type: "text/markdown" }),
    );
    await user.click(screen.getByRole("button", { name: "上传 1 个共享文件" }));

    expect(await screen.findByText("当前账号没有共享资料权限")).toBeInTheDocument();
    expect(screen.queryByText("denied.md")).not.toBeInTheDocument();
  });
});
