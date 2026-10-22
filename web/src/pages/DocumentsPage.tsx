import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { FileText, Plus, RefreshCw, Trash2, Upload } from "lucide-react";
import { type ChangeEvent, type FormEvent, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiError } from "../api/client";
import { newIdempotencyKey } from "../api/idempotency";
import { queryKeys } from "../api/queryKeys";
import type { DocumentItem } from "../api/types";
import { useAuth } from "../auth/context";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/Feedback";
import { LoadingRows } from "../components/LoadingRows";
import { useSessionGuard } from "../hooks/useSessionGuard";
import { userError } from "../utils/errors";
import { formatDate } from "../utils/format";
import { validateDocuments } from "../utils/documentValidation";

const documentStates: Record<DocumentItem["state"], { label: string; tone: string }> = {
  uploaded: { label: "已上传", tone: "uploaded" },
  processing: { label: "处理中", tone: "processing" },
  ready: { label: "可检索", tone: "ready" },
  failed: { label: "索引失败", tone: "failed" },
  deleted: { label: "已删除", tone: "deleted" },
};

function fileSignature(files: File[]): string {
  return files.map((file) => `${file.name}:${file.size}:${file.lastModified}`).join("|");
}

function DocumentRow({
  document,
  onDelete,
  deleting,
  canDelete = document.can_delete,
}: {
  document: DocumentItem;
  onDelete: () => void;
  deleting: boolean;
  canDelete?: boolean;
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
        <span className={`document-scope document-scope--${document.visibility}`}>
          {document.visibility === "shared" ? "共享" : "个人"}
        </span>
        <span className={`state-pill state-pill--${status.tone}`}>{status.label}</span>
        <span>{document.chunk_count} 个分块</span>
      </div>
      {canDelete && (
        <button
          type="button"
          className="icon-button icon-button--danger"
          aria-label={`删除 ${document.title}`}
          onClick={onDelete}
          disabled={deleting}
        >
          <Trash2 size={17} aria-hidden="true" />
        </button>
      )}
    </article>
  );
}

export function DocumentsPage() {
  const queryClient = useQueryClient();
  const { session } = useAuth();
  const isAdmin = session?.user.role === "admin";
  const fileInput = useRef<HTMLInputElement>(null);
  const sharedFileInput = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [sharedFiles, setSharedFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const [sharedFileError, setSharedFileError] = useState<string | null>(null);
  const [requestKey, setRequestKey] = useState<string | null>(null);
  const [requestedSignature, setRequestedSignature] = useState("");
  const [pendingDelete, setPendingDelete] = useState<DocumentItem | null>(null);
  const [deleteKey, setDeleteKey] = useState<string | null>(null);
  const [pendingSharedDelete, setPendingSharedDelete] = useState<DocumentItem | null>(null);
  const [sharedDeleteKey, setSharedDeleteKey] = useState<string | null>(null);

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

  const sharedDocuments = useInfiniteQuery({
    queryKey: [...queryKeys.documents, "shared"],
    queryFn: ({ pageParam }) => api.sharedDocuments(pageParam, 20),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) =>
        page.items.some((item) => item.state === "uploaded" || item.state === "processing"),
      )
        ? 1500
        : false,
  });
  useSessionGuard(sharedDocuments.error);

  const upload = useMutation({
    mutationFn: ({
      selectedFiles,
      key,
    }: {
      selectedFiles: File[];
      key: string;
    }) => api.uploadDocuments(selectedFiles, key),
    onSuccess: () => {
      setFiles([]);
      setRequestKey(null);
      if (fileInput.current) {
        fileInput.current.value = "";
      }
      void queryClient.invalidateQueries({
        queryKey: queryKeys.documents,
        predicate: (query) => query.queryKey.length === 1,
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });

  const remove = useMutation({
    mutationFn: ({ document, key }: { document: DocumentItem; key: string }) =>
      api.deleteDocument(document.id, key),
    onSuccess: () => {
      setPendingDelete(null);
      setDeleteKey(null);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.documents,
        predicate: (query) => query.queryKey.length === 1,
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });

  const uploadShared = useMutation({
    mutationFn: ({ selectedFiles, key }: { selectedFiles: File[]; key: string }) =>
      api.uploadSharedDocuments(selectedFiles, key),
    onSuccess: () => {
      setSharedFiles([]);
      setSharedFileError(null);
      if (sharedFileInput.current) {
        sharedFileInput.current.value = "";
      }
      void queryClient.invalidateQueries({ queryKey: [...queryKeys.documents, "shared"] });
    },
  });

  const removeShared = useMutation({
    mutationFn: ({ document, key }: { document: DocumentItem; key: string }) =>
      api.deleteSharedDocument(document.id, key),
    onSuccess: () => {
      setPendingSharedDelete(null);
      setSharedDeleteKey(null);
      void queryClient.invalidateQueries({ queryKey: [...queryKeys.documents, "shared"] });
    },
  });

  const handleFile = (event: ChangeEvent<HTMLInputElement>) => {
    const nextFiles = Array.from(event.target.files ?? []);
    setFiles(nextFiles);
    setFileError(validateDocuments(nextFiles));
    setRequestKey(null);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const error = validateDocuments(files);
    setFileError(error);
    if (error || files.length === 0) {
      return;
    }
    let key = requestKey;
    const signature = fileSignature(files);
    if (!key || requestedSignature !== signature) {
      key = newIdempotencyKey();
      setRequestKey(key);
      setRequestedSignature(signature);
    }
    upload.mutate({ selectedFiles: files, key });
  };

  const handleSharedFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const nextFiles = Array.from(event.target.files ?? []);
    setSharedFiles(nextFiles);
    setSharedFileError(validateDocuments(nextFiles));
  };

  const submitShared = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const error = validateDocuments(sharedFiles);
    setSharedFileError(error);
    if (error || sharedFiles.length === 0) {
      return;
    }
    uploadShared.mutate({
      selectedFiles: sharedFiles,
      key: newIdempotencyKey(),
    });
  };

  const conflict =
    upload.error instanceof ApiError && upload.error.code === "idempotency_conflict";
  const items = documents.data?.pages.flatMap((page) => page.items) ?? [];
  const sharedItems = sharedDocuments.data?.pages.flatMap((page) => page.items) ?? [];

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
                <strong>
                  {files.length > 0
                    ? `已选择 ${files.length} 个文件`
                    : "选择 PDF、DOCX、TXT 或 Markdown"}
                </strong>
                <small>
                  {files.length > 0
                    ? files.map((file) => file.name).join("、")
                    : "可多选，单个文件最大 10 MB"}
                </small>
              </span>
              <input
                ref={fileInput}
                id="document-file"
                className="visually-hidden"
                type="file"
                accept=".pdf,.docx,.txt,.md,application/pdf,text/plain,text/markdown"
                multiple
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
          {upload.isError && (
            <ErrorNotice
              message={userError(upload.error)}
              onRetry={
                conflict
                  ? undefined
                  : () =>
                      upload.mutate({
                        selectedFiles: files,
                        key: requestKey ?? newIdempotencyKey(),
                      })
              }
            />
          )}
          <button
            className="primary-button"
            type="submit"
            disabled={upload.isPending || files.length === 0}
          >
            <Upload size={17} aria-hidden="true" />
            <span>{upload.isPending ? "正在上传" : `上传 ${files.length || ""} 个文件`}</span>
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

      <section className="content-section" aria-labelledby="shared-library-title">
        <div className="section-heading">
          <div className="section-heading-copy">
            <p className="section-kicker">SHARED / LIBRARY</p>
            <h2 id="shared-library-title">共享资料</h2>
            <p>管理员上传的资料对所有账号可见，并自动参与检索问答。</p>
          </div>
          <span className="result-count">{sharedItems.length} 份资料</span>
        </div>
        {isAdmin && (
          <form className="documents-form shared-documents-form" onSubmit={submitShared} noValidate>
            <div className="field">
              <label htmlFor="shared-document-file">共享资料文件</label>
              <label className={`file-picker ${sharedFileError ? "file-picker--error" : ""}`}>
                <FileText size={22} aria-hidden="true" />
                <span>
                  <strong>
                    {sharedFiles.length > 0
                      ? `已选择 ${sharedFiles.length} 个共享文件`
                      : "选择要共享给所有账号的资料"}
                  </strong>
                  <small>仅管理员可上传，单个文件最大 10 MB</small>
                </span>
                <input
                  ref={sharedFileInput}
                  id="shared-document-file"
                  className="visually-hidden"
                  type="file"
                  accept=".pdf,.docx,.txt,.md,application/pdf,text/plain,text/markdown"
                  multiple
                  onChange={handleSharedFiles}
                  disabled={uploadShared.isPending}
                />
              </label>
              {sharedFileError && (
                <p className="field-error" role="alert">
                  {sharedFileError}
                </p>
              )}
            </div>
            {uploadShared.isError && <ErrorNotice message={userError(uploadShared.error)} />}
            <button
              className="primary-button"
              type="submit"
              disabled={uploadShared.isPending || sharedFiles.length === 0}
            >
              <Upload size={17} aria-hidden="true" />
              <span>
                {uploadShared.isPending
                  ? "正在上传共享资料"
                  : `上传 ${sharedFiles.length || ""} 个共享文件`}
              </span>
            </button>
          </form>
        )}
        {sharedDocuments.isPending && <LoadingRows rows={3} />}
        {sharedDocuments.isError && sharedItems.length === 0 && (
          <ErrorNotice
            message={userError(sharedDocuments.error)}
            onRetry={() => void sharedDocuments.refetch()}
          />
        )}
        {sharedDocuments.isSuccess && sharedItems.length === 0 && (
          <EmptyState
            title="还没有共享资料"
            description="管理员上传后，所有账号都能在这里查看。"
          />
        )}
        {sharedItems.length > 0 && (
          <div className="document-list">
            {sharedItems.map((document) => (
              <DocumentRow
                key={document.id}
                document={document}
                canDelete={isAdmin}
                deleting={removeShared.isPending && pendingSharedDelete?.id === document.id}
                onDelete={() => {
                  setPendingSharedDelete(document);
                  setSharedDeleteKey(newIdempotencyKey());
                }}
              />
            ))}
          </div>
        )}
        {sharedDocuments.hasNextPage && (
          <button
            type="button"
            className="secondary-button load-more-button"
            onClick={() => void sharedDocuments.fetchNextPage()}
            disabled={sharedDocuments.isFetchingNextPage}
          >
            <RefreshCw size={16} aria-hidden="true" />
            <span>{sharedDocuments.isFetchingNextPage ? "正在加载" : "加载更多"}</span>
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

      {pendingSharedDelete && (
        <div className="modal-scrim" role="presentation">
          <section
            className="confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-shared-document-title"
          >
            <p className="eyebrow">DELETE / SHARED DOCUMENT</p>
            <h2 id="delete-shared-document-title">删除这份共享资料？</h2>
            <p>删除后所有账号都将无法继续检索，历史回答中的来源会标记为已删除。</p>
            {removeShared.isError && (
              <ErrorNotice message={userError(removeShared.error)} compact />
            )}
            <div className="dialog-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setPendingSharedDelete(null)}
                disabled={removeShared.isPending}
              >
                取消
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={() =>
                  removeShared.mutate({
                    document: pendingSharedDelete,
                    key: sharedDeleteKey ?? newIdempotencyKey(),
                  })
                }
                disabled={removeShared.isPending}
              >
                <Trash2 size={17} aria-hidden="true" />
                <span>{removeShared.isPending ? "正在删除" : "确认删除"}</span>
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
