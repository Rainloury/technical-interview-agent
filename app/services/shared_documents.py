"""管理员管理的共享文档上传、列出、详情和删除。"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.jobs import enqueue_job
from app.db.models import (
    AsyncJob,
    QaEvidence,
    SharedDocument,
    SharedDocumentChunk,
    User,
)
from app.errors import AppError
from app.schemas.documents import (
    DocumentAccepted,
    DocumentBatchAccepted,
    DocumentItem,
    DocumentPage,
    DocumentUpload,
)
from app.services._audit import audit
from app.services._idempotency import operation_key
from app.services._ownership import get_owned
from app.services._pagination import Cursor, cursor_condition, decode_cursor, encode_cursor
from app.services._storage_tx import (
    UploadObjects,
    put_object,
    rollback_with_object_cleanup,
    uploaded_object_keys,
)
from app.services.documents import (
    safe_document_name,
    validate_document_identity,
)
from app.storage import ObjectStorage


def _key(operation: str, actor_id: uuid.UUID, client_key: str) -> str:
    return operation_key(operation, actor_id, client_key)


def _item(document: SharedDocument, *, can_delete: bool) -> DocumentItem:
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
        retention_expires_at=document.created_at,
        visibility="shared",
        can_delete=can_delete,
    )


async def _document(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    include_deleted: bool = False,
) -> SharedDocument:
    return await get_owned(
        session,
        SharedDocument,
        None,
        document_id,
        message="资料不存在",
        include_deleted=include_deleted,
        with_owner_scope=False,
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
    request_id: str,
) -> DocumentAccepted:
    filename = safe_document_name(upload.filename)
    detected_mime = validate_document_identity(
        filename=filename,
        declared_mime=upload.declared_mime,
        content=upload.content,
        settings=settings,
    )
    content_hash = hashlib.sha256(upload.content).hexdigest()
    title = (upload.title or "").strip()[:120] or filename
    fingerprint = hashlib.sha256(
        b"\0".join([filename.encode(), (upload.declared_mime or "").encode(), upload.content])
    ).hexdigest()
    stored_key = _key("shared-document-upload", user.id, idempotency_key)

    existing_job = (
        await session.execute(select(AsyncJob).where(AsyncJob.idempotency_key == stored_key))
    ).scalar_one_or_none()
    if existing_job is not None:
        if existing_job.request_fingerprint != fingerprint:
            raise AppError(
                status_code=409,
                code="idempotency_conflict",
                message="该幂等键已用于其他共享资料",
            )
        existing = await _document(session, existing_job.resource_id)
        return DocumentAccepted(
            document_id=existing.id,
            state=existing.state,
            created_at=existing.created_at,
        )

    existing_by_hash = (
        await session.execute(
            select(SharedDocument)
            .where(
                SharedDocument.sha256 == content_hash,
                SharedDocument.deleted_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if existing_by_hash is not None:
        return DocumentAccepted(
            document_id=existing_by_hash.id,
            state=existing_by_hash.state,
            created_at=existing_by_hash.created_at,
        )

    document = SharedDocument(
        created_by_user_id=user.id,
        title=title,
        original_filename=filename,
        detected_mime=detected_mime,
        size_bytes=len(upload.content),
        sha256=content_hash,
        object_key=f"shared/{uuid.uuid4().hex}/{uuid.uuid4().hex}",
        state="uploaded",
        request_fingerprint=fingerprint,
        idempotency_key=stored_key,
    )
    session.add(document)
    await session.flush()
    await put_object(storage, document.object_key, upload.content, uploaded=uploaded)
    await enqueue_job(
        session,
        owner_user_id=user.id,
        job_type="process_document",
        resource_type="shared_document",
        resource_id=document.id,
        idempotency_key=f"process-shared-document:{document.id.hex}:{uuid.uuid4().hex}",
        request_fingerprint=fingerprint,
        max_attempts=settings.worker_max_attempts,
    )
    await audit(
        session,
        action="shared_document_uploaded",
        resource_type="shared_document",
        resource_id_hash=hashlib.sha256(document.id.bytes).hexdigest(),
        result="success",
        request_id=request_id,
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
    request_id: str,
) -> DocumentAccepted:
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
            request_id=request_id,
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
    request_id: str,
) -> DocumentBatchAccepted:
    if not uploads:
        raise AppError(status_code=422, code="invalid_request", message="至少选择一个资料文件")
    identities = [
        (upload.filename, hashlib.sha256(upload.content).hexdigest()) for upload in uploads
    ]
    if len(identities) != len(set(identities)):
        raise AppError(
            status_code=422,
            code="invalid_request",
            message="同一批次不能重复上传相同文件",
        )
    accepted: list[DocumentAccepted] = []
    uploaded = uploaded_object_keys()
    try:
        for upload in uploads:
            item_key = (
                f"{idempotency_key}:{upload.filename}:{hashlib.sha256(upload.content).hexdigest()}"
            )
            item = await _store_document(
                session,
                storage,
                user,
                upload,
                idempotency_key=item_key,
                settings=settings,
                uploaded=uploaded,
                request_id=request_id,
            )
            accepted.append(item)
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
    *,
    is_admin: bool,
    limit: int = 20,
    cursor: str | None = None,
) -> DocumentPage:
    query = select(SharedDocument).where(SharedDocument.deleted_at.is_(None))
    if cursor:
        parsed = decode_cursor(cursor)
        query = query.where(cursor_condition(SharedDocument.created_at, SharedDocument.id, parsed))
    rows = list(
        (
            await session.execute(
                query.order_by(SharedDocument.created_at.desc(), SharedDocument.id.desc()).limit(
                    limit + 1
                )
            )
        ).scalars()
    )
    has_more = len(rows) > limit
    items = rows[:limit]
    return DocumentPage(
        items=[_item(document, can_delete=is_admin) for document in items],
        next_cursor=(
            encode_cursor(Cursor(timestamp=items[-1].created_at, id=items[-1].id))
            if has_more and items
            else None
        ),
    )


async def get_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    is_admin: bool,
) -> DocumentItem:
    return _item(
        await _document(session, document_id),
        can_delete=is_admin,
    )


async def delete_document(
    session: AsyncSession,
    user: User,
    document_id: uuid.UUID,
    *,
    idempotency_key: str,
    settings: Settings,
    request_id: str,
) -> None:
    document = await _document(session, document_id, include_deleted=True)
    if document.state == "deleted":
        return
    operation_key = _key("delete-shared-document", user.id, idempotency_key)
    fingerprint = hashlib.sha256(f"delete-shared-document\0{document.id.hex}".encode()).hexdigest()
    existing_job = (
        await session.execute(select(AsyncJob).where(AsyncJob.idempotency_key == operation_key))
    ).scalar_one_or_none()
    if existing_job is not None:
        if existing_job.request_fingerprint != fingerprint:
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
    chunk_ids = select(SharedDocumentChunk.id).where(SharedDocumentChunk.document_id == document.id)
    await session.execute(
        update(QaEvidence)
        .where(QaEvidence.shared_document_chunk_id.in_(chunk_ids))
        .values(source_state="source_deleted")
    )
    await enqueue_job(
        session,
        owner_user_id=user.id,
        job_type="delete_document",
        resource_type="shared_document",
        resource_id=document.id,
        idempotency_key=operation_key,
        request_fingerprint=fingerprint,
        max_attempts=settings.worker_max_attempts,
    )
    await audit(
        session,
        action="shared_document_deleted",
        resource_type="shared_document",
        resource_id_hash=hashlib.sha256(document.id.bytes).hexdigest(),
        result="success",
        request_id=request_id,
    )
    await session.commit()
