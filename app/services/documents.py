"""按所有者范围的私有文档上传、列表、详情与删除。"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import filetype
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.jobs import enqueue_job
from app.db.models import AsyncJob, QaEvidence, User, UserDocument, UserDocumentChunk
from app.errors import AppError
from app.schemas.documents import (
    DocumentAccepted,
    DocumentBatchAccepted,
    DocumentItem,
    DocumentPage,
    DocumentUpload,
)
from app.services._documents_common import batch_item_key, document_item, validate_batch
from app.services._idempotency import operation_key
from app.services._ownership import get_owned
from app.services._pagination import Cursor, cursor_condition, decode_cursor, encode_cursor
from app.services._storage_tx import (
    UploadObjects,
    put_object,
    rollback_with_object_cleanup,
    uploaded_object_keys,
)
from app.storage import ObjectStorage

SUPPORTED_MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


def _key(operation: str, owner_id: uuid.UUID, client_key: str) -> str:
    return operation_key(operation, owner_id, client_key)


def safe_document_name(filename: str) -> str:
    name = Path(filename or "").name.strip()
    name = "".join(char for char in name if char.isprintable())
    if not name:
        raise AppError(
            status_code=422,
            code="unsupported_source",
            message="请选择支持的资料文件",
        )
    return name[:255]


def validate_document_identity(
    *,
    filename: str,
    declared_mime: str | None,
    content: bytes,
    settings: Settings,
) -> str:
    if not content:
        raise AppError(status_code=422, code="invalid_request", message="文件不能为空")
    if len(content) > settings.document_max_bytes:
        raise AppError(status_code=413, code="file_too_large", message="文件不能超过 10 MB")
    suffix = Path(filename).suffix.lower()
    expected = SUPPORTED_MIME_BY_SUFFIX.get(suffix)
    if expected is None:
        raise AppError(
            status_code=422,
            code="unsupported_source",
            message="仅支持 PDF、DOCX、TXT 或 Markdown 资料",
        )
    declared = (declared_mime or "").split(";", 1)[0].strip().lower()
    if declared and declared not in {expected, "text/plain"}:
        raise AppError(
            status_code=422,
            code="unsupported_source",
            message="文件类型与扩展名不一致",
        )
    if expected in {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        detected = filetype.guess(content)
        detected_mime = getattr(detected, "mime", None)
        if detected_mime != expected:
            raise AppError(
                status_code=422,
                code="unsupported_source",
                message="文件内容不是有效的 PDF 或 DOCX",
            )
    return expected


def _item(document: UserDocument) -> DocumentItem:
    return document_item(
        document,
        visibility="private",
        can_delete=True,
        retention_expires_at=document.retention_expires_at,
    )


async def _owned_document(
    session: AsyncSession,
    user: User,
    document_id: uuid.UUID,
    *,
    include_deleted: bool = False,
) -> UserDocument:
    return await get_owned(
        session,
        UserDocument,
        user,
        document_id,
        message="资料不存在",
        include_deleted=include_deleted,
    )


async def _store_document(
    session: AsyncSession,
    storage: ObjectStorage,
    user: User,
    upload: DocumentUpload,
    *,
    idempotency_key: str,
    settings: Settings,
    uploaded: UploadObjects,
) -> DocumentAccepted:
    """在不提交的情况下验证、私有存储并将一个文档入队。"""

    filename = safe_document_name(upload.filename)
    detected_mime = validate_document_identity(
        filename=filename,
        declared_mime=upload.declared_mime,
        content=upload.content,
        settings=settings,
    )
    sha256 = hashlib.sha256(upload.content).hexdigest()
    title = (upload.title or "").strip()[:120] or filename
    fingerprint = hashlib.sha256(
        b"\0".join(
            (
                filename.encode(),
                (upload.declared_mime or "").encode(),
                upload.content,
            )
        )
    ).hexdigest()
    stored_key = _key("document-upload", user.id, idempotency_key)
    existing_job = (
        await session.execute(select(AsyncJob).where(AsyncJob.idempotency_key == stored_key))
    ).scalar_one_or_none()
    if existing_job is not None:
        if existing_job.request_fingerprint != fingerprint:
            raise AppError(
                status_code=409,
                code="idempotency_conflict",
                message="该幂等键已用于其他资料",
            )
        existing_document = await _owned_document(session, user, existing_job.resource_id)
        return DocumentAccepted(
            document_id=existing_document.id,
            state=existing_document.state,
            created_at=existing_document.created_at,
        )

    existing_by_key = (
        await session.execute(
            select(UserDocument).where(
                UserDocument.owner_user_id == user.id,
                UserDocument.idempotency_key == stored_key,
                UserDocument.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing_by_key is not None:
        if existing_by_key.request_fingerprint != fingerprint:
            raise AppError(
                status_code=409,
                code="idempotency_conflict",
                message="该幂等键已用于其他资料",
            )
        return DocumentAccepted(
            document_id=existing_by_key.id,
            state=existing_by_key.state,
            created_at=existing_by_key.created_at,
        )

    stored_document = (
        await session.execute(
            select(UserDocument)
            .where(
                UserDocument.owner_user_id == user.id,
                UserDocument.sha256 == sha256,
                UserDocument.deleted_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    object_key = f"{user.id.hex}/documents/{uuid.uuid4().hex}"
    if stored_document is not None and stored_document.state in {"uploaded", "processing", "ready"}:
        return DocumentAccepted(
            document_id=stored_document.id,
            state=stored_document.state,
            created_at=stored_document.created_at,
        )
    if stored_document is None:
        document = UserDocument(
            owner_user_id=user.id,
            title=title,
            original_filename=filename,
            detected_mime=detected_mime,
            size_bytes=len(upload.content),
            sha256=sha256,
            object_key=object_key,
            state="uploaded",
            request_fingerprint=fingerprint,
            retention_expires_at=datetime.now(UTC) + timedelta(days=90),
        )
        session.add(document)
        await put_object(storage, object_key, upload.content, uploaded=uploaded)
        await session.flush()
    else:
        document = stored_document
        document.title = title
        document.original_filename = filename
        document.detected_mime = detected_mime
        document.size_bytes = len(upload.content)
        document.state = "uploaded"
        document.failure_code = None
        document.error_message = None
        document.completed_at = None
        await put_object(storage, document.object_key, upload.content, uploaded=uploaded)
    document.idempotency_key = stored_key
    document.updated_at = datetime.now(UTC)
    await session.flush()
    await enqueue_job(
        session,
        owner_user_id=user.id,
        job_type="process_document",
        resource_type="user_document",
        resource_id=document.id,
        idempotency_key=f"process-document:{document.id.hex}:{uuid.uuid4().hex}",
        request_fingerprint=fingerprint,
        max_attempts=settings.worker_max_attempts,
    )
    return DocumentAccepted(
        document_id=document.id,
        state=document.state,
        created_at=document.created_at,
    )


async def upload_document(
    session: AsyncSession,
    storage: ObjectStorage,
    user: User,
    upload: DocumentUpload,
    *,
    idempotency_key: str,
    settings: Settings,
) -> DocumentAccepted:
    """验证、私有存储、入队并提交一个文档。"""

    uploaded = uploaded_object_keys()
    try:
        accepted = await _store_document(
            session,
            storage,
            user,
            upload,
            idempotency_key=idempotency_key,
            settings=settings,
            uploaded=uploaded,
        )
        await session.commit()
        return accepted
    except Exception:
        await rollback_with_object_cleanup(session, storage, uploaded)
        raise


async def upload_documents(
    session: AsyncSession,
    storage: ObjectStorage,
    user: User,
    uploads: list[DocumentUpload],
    *,
    idempotency_key: str,
    settings: Settings,
) -> DocumentBatchAccepted:
    """在一个原子批次中存储并将每个文件入队。"""

    validate_batch(uploads)
    accepted: list[DocumentAccepted] = []
    uploaded = uploaded_object_keys()
    try:
        for upload in uploads:
            item_key = batch_item_key(idempotency_key, upload)
            accepted_item = await _store_document(
                session,
                storage,
                user,
                upload,
                idempotency_key=item_key,
                settings=settings,
                uploaded=uploaded,
            )
            accepted.append(accepted_item)
        await session.commit()
    except Exception:
        await rollback_with_object_cleanup(session, storage, uploaded)
        raise
    return DocumentBatchAccepted(
        documents=accepted,
        original_filenames=[safe_document_name(upload.filename) for upload in uploads],
    )


async def list_documents(
    session: AsyncSession,
    user: User,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> DocumentPage:
    """返回稳定的按所有者范围的文档分页。"""

    now = datetime.now(UTC)
    query = select(UserDocument).where(
        UserDocument.owner_user_id == user.id,
        UserDocument.deleted_at.is_(None),
        UserDocument.retention_expires_at > now,
    )
    if cursor:
        parsed = decode_cursor(cursor)
        query = query.where(cursor_condition(UserDocument.created_at, UserDocument.id, parsed))
    rows = list(
        (
            await session.execute(
                query.order_by(UserDocument.created_at.desc(), UserDocument.id.desc()).limit(
                    limit + 1
                )
            )
        ).scalars()
    )
    has_more = len(rows) > limit
    items = rows[:limit]
    return DocumentPage(
        items=[_item(document) for document in items],
        next_cursor=(
            encode_cursor(Cursor(timestamp=items[-1].created_at, id=items[-1].id))
            if has_more and items
            else None
        ),
    )


async def get_document(
    session: AsyncSession,
    user: User,
    document_id: uuid.UUID,
) -> DocumentItem:
    return _item(await _owned_document(session, user, document_id))


async def delete_document(
    session: AsyncSession,
    user: User,
    document_id: uuid.UUID,
    *,
    idempotency_key: str,
    settings: Settings,
) -> None:
    """立即将一个文档标记为墓碑并私有清理入队。"""

    document = await _owned_document(session, user, document_id, include_deleted=True)
    if document.state == "deleted":
        return
    operation_key = _key("delete-document", user.id, idempotency_key)
    operation_fingerprint = hashlib.sha256(
        f"delete-document\0{document.id.hex}".encode()
    ).hexdigest()
    existing_job = (
        await session.execute(select(AsyncJob).where(AsyncJob.idempotency_key == operation_key))
    ).scalar_one_or_none()
    if existing_job is not None:
        if existing_job.request_fingerprint != operation_fingerprint:
            raise AppError(
                status_code=409,
                code="idempotency_conflict",
                message="该幂等键已用于其他删除请求",
            )
        return
    now = datetime.now(UTC)
    document.state = "deleted"
    document.deletion_state = "pending"
    document.deleted_at = now
    document.updated_at = now
    chunk_ids = select(UserDocumentChunk.id).where(UserDocumentChunk.document_id == document.id)
    await session.execute(
        update(QaEvidence)
        .where(QaEvidence.user_document_chunk_id.in_(chunk_ids))
        .values(source_state="source_deleted")
    )
    await enqueue_job(
        session,
        owner_user_id=user.id,
        job_type="delete_document",
        resource_type="user_document",
        resource_id=document.id,
        idempotency_key=operation_key,
        request_fingerprint=operation_fingerprint,
        max_attempts=settings.worker_max_attempts,
    )
    await session.commit()
