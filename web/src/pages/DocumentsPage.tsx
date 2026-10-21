import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { FileText, Plus, RefreshCw, Trash2, Upload } from "lucide-react";
import { type ChangeEvent, type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiError } from "../api/client";
import { newIdempotencyKey } from "../api/idempotency";
import { queryKeys } from "../api/queryKeys";
import type { DocumentItem } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/Feedback";
import { LoadingRows } from "../components/LoadingRows";
import { useSessionGuard } from "../hooks/useSessionGuard";
import { userError } from "../utils/errors";
import { formatDate } from "../utils/format";
import { validateDocument } from "../utils/documentValidation";

const documentStates: Record<DocumentItem["state"], { label: string; tone: string }> = {
  uploaded: { label: "已上传", tone: "uploaded" },
  processing: { label: "处理中", tone: "processing" },
  ready: { label: "可检索", tone: "ready" },
  failed: { label: "索引失败", tone: "failed" },
  deleted: { label: "已删除", tone: "deleted" },
};

function DocumentRow({
  document,
  onDelete,
  deleting,
}: {
  document: DocumentItem;
  onDelete: () => void;
  deleting: boolean;
}) {
  const status = documentStates[document.state];
  return (
    <article className="document-row">
      <span className="record-type" aria-hidden="true">
        <FileText size={18} />
      </span>
      <div className="record-copy">
        <strong title={document.title}>{document.title}</strong>
        <span>
          {document.original_filename} · {formatDate(document.updated_at)}
        </span>
      </div>
      <div className="document-meta">
        <span className={`state-pill state-pill--${status.tone}`}>{status.label}</span>
        <span>{document.chunk_count} 个分块</span>
      </div>
      <button
        type="button"
        className="icon-button icon-button--danger"
        aria-label={`删除 ${document.title}`}
        onClick={onDelete}
        disabled={deleting}
      >
        <Trash2 size={17} aria-hidden="true" />
      </button>
    </article>
  );
}

export function DocumentsPage() {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [requestKey, setRequestKey] = useState<string | null>(null);
  const [requestedFile, setRequestedFile] = useState<File | null>(null);
  const [requestedTitle, setRequestedTitle] = useState("");
  const [pendingDelete, setPendingDelete] = useState<DocumentItem | null>(null);
  const [deleteKey, setDeleteKey] = useState<string | null>(null);

  const documents = useInfiniteQuery({
    queryKey: queryKeys.documents,
    queryFn: ({ pageParam }) => api.documents(pageParam, 20),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) =>
        page.items.some((item) => item.state === "uploaded" || item.state === "processing"),
      )
        ? 1500
        : false,
  });
  useSessionGuard(documents.error);

  const upload = useMutation({
    mutationFn: ({
      selectedFile,
      selectedTitle,
      key,
    }: {
      selectedFile: File;
      selectedTitle: string;
      key: string;
    }) => api.uploadDocument(selectedFile, selectedTitle, key),
    onSuccess: () => {
      setFile(null);
      setTitle("");
      setRequestKey(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });

  const remove = useMutation({
    mutationFn: ({ document, key }: { document: DocumentItem; key: string }) =>
      api.deleteDocument(document.id, key),
    onSuccess: () => {
      setPendingDelete(null);
      setDeleteKey(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });

  const handleFile = (event: ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0] ?? null;
    setFile(nextFile);
    setFileError(validateDocument(nextFile));
    setRequestKey(null);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const error = validateDocument(file);
    setFileError(error);
    if (error || !file) {
      return;
    }
    let key = requestKey;
    if (!key || requestedFile !== file || requestedTitle !== title) {
      key = newIdempotencyKey();
      setRequestKey(key);
      setRequestedFile(file);
      setRequestedTitle(title);
    }
    upload.mutate({ selectedFile: file, selectedTitle: title, key });
  };

  const conflict =
    upload.error instanceof ApiError && upload.error.code === "idempotency_conflict";
  const items = documents.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="page documents-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">LIBRARY / PRIVATE DOCUMENTS</p>
          <h1>内部资料</h1>
          <p className="page-lede">
            上传当前账号的技术资料，索引完成后自动加入检索问答，不与其他账号共享。
          </p>
        </div>
        <Link className="secondary-button secondary-button--link" to="/workspace">
          <Plus size={17} aria-hidden="true" />
          <span>返回工作台</span>
        </Link>
      </header>

      <section className="content-section documents-upload-section" aria-labelledby="upload-title">
        <div className="section-heading">
          <div className="section-heading-copy">
            <p className="section-kicker">UPLOAD</p>
            <h2 id="upload-title">新增资料</h2>
          </div>
        </div>
        <form className="documents-form" onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="document-file">资料文件</label>
            <label className={`file-picker ${fileError ? "file-picker--error" : ""}`}>
              <FileText size={22} aria-hidden="true" />
              <span>
                <strong>{file?.name ?? "选择 PDF、DOCX、TXT 或 Markdown"}</strong>
                <small>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "最大 10 MB"}</small>
              </span>
              <input
                id="document-file"
                className="visually-hidden"
                type="file"
                accept=".pdf,.docx,.txt,.md,application/pdf,text/plain,text/markdown"
                onChange={handleFile}
                disabled={upload.isPending}
              />
            </label>
            {fileError && (
              <p className="field-error" role="alert">
                {fileError}
              </p>
            )}
          </div>
          <div className="field">
            <label htmlFor="document-title">资料标题</label>
            <input
              id="document-title"
              className="text-input"
              value={title}
              maxLength={120}
              placeholder="可选，默认使用文件名"
              onChange={(event) => {
                setTitle(event.target.value);
                setRequestKey(null);
              }}
              disabled={upload.isPending}
            />
          </div>
          {upload.isError && (
            <ErrorNotice
              message={userError(upload.error)}
              onRetry={
                conflict
                  ? undefined
                  : () =>
                      upload.mutate({
                        selectedFile: file!,
                        selectedTitle: title,
                        key: requestKey ?? newIdempotencyKey(),
                      })
              }
            />
          )}
          <button className="primary-button" type="submit" disabled={upload.isPending || !file}>
            <Upload size={17} aria-hidden="true" />
            <span>{upload.isPending ? "正在上传" : "上传资料"}</span>
          </button>
        </form>
      </section>

      <section className="content-section" aria-labelledby="library-title">
        <div className="section-heading">
          <div className="section-heading-copy">
            <p className="section-kicker">LIBRARY</p>
            <h2 id="library-title">资料列表</h2>
          </div>
          <span className="result-count">{items.length} 份资料</span>
        </div>
        {documents.isPending && <LoadingRows rows={4} />}
        {documents.isError && items.length === 0 && (
          <ErrorNotice message={userError(documents.error)} onRetry={() => void documents.refetch()} />
        )}
        {documents.isSuccess && items.length === 0 && (
          <EmptyState
            title="还没有内部资料"
            description="上传第一份资料后，系统会在后台完成解析与索引。"
            action={
              <a className="text-button text-button--link" href="#document-file">
                上传第一份资料
              </a>
            }
          />
        )}
        {items.length > 0 && (
          <div className="document-list">
            {items.map((document) => (
              <DocumentRow
                key={document.id}
                document={document}
                deleting={remove.isPending && pendingDelete?.id === document.id}
                onDelete={() => {
                  setPendingDelete(document);
                  setDeleteKey(newIdempotencyKey());
                }}
              />
            ))}
          </div>
        )}
        {documents.hasNextPage && (
          <button
            type="button"
            className="secondary-button load-more-button"
            onClick={() => void documents.fetchNextPage()}
            disabled={documents.isFetchingNextPage}
          >
            <RefreshCw size={16} aria-hidden="true" />
            <span>{documents.isFetchingNextPage ? "正在加载" : "加载更多"}</span>
          </button>
        )}
      </section>

      {pendingDelete && (
        <div className="modal-scrim" role="presentation">
          <section
            className="confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-document-title"
          >
            <p className="eyebrow">DELETE / DOCUMENT</p>
            <h2 id="delete-document-title">删除这份资料？</h2>
            <p>删除后不会继续参与检索，历史回答中的来源会标记为已删除。</p>
            {remove.isError && <ErrorNotice message={userError(remove.error)} compact />}
            <div className="dialog-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setPendingDelete(null)}
                disabled={remove.isPending}
              >
                取消
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={() =>
                  remove.mutate({
                    document: pendingDelete,
                    key: deleteKey ?? newIdempotencyKey(),
                  })
                }
                disabled={remove.isPending}
              >
                <Trash2 size={17} aria-hidden="true" />
                <span>{remove.isPending ? "正在删除" : "确认删除"}</span>
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
