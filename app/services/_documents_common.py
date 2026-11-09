"""私有与共享文档 service 的共享视图与批次校验。"""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from app.errors import AppError
from app.schemas.documents import DocumentItem, DocumentUpload


class DocumentRow(Protocol):
    """两个文档表共有的公开视图字段。"""

    id: Any
    title: str
    original_filename: str
    state: str
    chunk_count: int
    failure_code: str | None
    error_message: str | None
    index_version: str | None
    created_at: Any
    updated_at: Any
    completed_at: Any


def document_item(
    document: DocumentRow,
    *,
    visibility: str,
    can_delete: bool,
    retention_expires_at: Any | None = None,
) -> DocumentItem:
    return DocumentItem(
        id=document.id,
        title=document.title,
        original_filename=document.original_filename,
        state=document.state,
        chunk_count=document.chunk_count,
        failure_code=document.failure_code,
        error_message=document.error_message,
        index_version=document.index_version,
        created_at=document.created_at,
        updated_at=document.updated_at,
        completed_at=document.completed_at,
        retention_expires_at=retention_expires_at or document.created_at,
        visibility=visibility,
        can_delete=can_delete,
    )


def validate_batch(uploads: list[DocumentUpload]) -> None:
    if not uploads:
        raise AppError(
            status_code=422,
            code="invalid_request",
            message="至少选择一个资料文件",
        )
    identities = [
        (upload.filename, hashlib.sha256(upload.content).hexdigest()) for upload in uploads
    ]
    if len(identities) != len(set(identities)):
        raise AppError(
            status_code=422,
            code="invalid_request",
            message="同一批次不能重复上传相同文件",
        )


def batch_item_key(idempotency_key: str, upload: DocumentUpload) -> str:
    content_hash = hashlib.sha256(upload.content).hexdigest()
    return f"{idempotency_key}:{upload.filename}:{content_hash}"
