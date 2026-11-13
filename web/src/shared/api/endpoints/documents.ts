import { request } from "@/shared/api/http";
import type { DocumentAccepted, DocumentBatchAccepted, DocumentItem, DocumentPage } from "@/shared/api/types";

export const documentsEndpoints = {
  documents: (cursor?: string | null, limit = 20) =>
    request<DocumentPage>("/api/v1/documents", {
      query: { cursor, limit },
    }),
  document: (id: string) => request<DocumentItem>(`/api/v1/documents/${id}`),
  uploadDocument: (file: File, title: string, idempotencyKey: string) => {
    const formData = new FormData();
    formData.set("file", file);
    if (title.trim()) {
      formData.set("title", title.trim());
    }
    return request<DocumentAccepted>("/api/v1/documents", {
      method: "POST",
      formData,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
  uploadDocuments: (files: File[], idempotencyKey: string) => {
    const formData = new FormData();
    for (const file of files) {
      formData.append("files", file);
    }
    return request<DocumentBatchAccepted>("/api/v1/documents/batch", {
      method: "POST",
      formData,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
  sharedDocuments: (cursor?: string | null, limit = 20) =>
    request<DocumentPage>("/api/v1/shared-documents", {
      query: { cursor, limit },
    }),
  uploadSharedDocuments: (files: File[], idempotencyKey: string) => {
    const formData = new FormData();
    for (const file of files) {
      formData.append("files", file);
    }
    return request<DocumentBatchAccepted>("/api/v1/shared-documents/batch", {
      method: "POST",
      formData,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
  deleteDocument: (id: string, idempotencyKey: string) =>
    request<void>(`/api/v1/documents/${id}`, {
      method: "DELETE",
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  deleteSharedDocument: (id: string, idempotencyKey: string) =>
    request<void>(`/api/v1/shared-documents/${id}`, {
      method: "DELETE",
      headers: { "Idempotency-Key": idempotencyKey },
    }),
};
