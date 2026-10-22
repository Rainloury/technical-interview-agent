"""Administrator-managed shared document upload, listing, detail, and deletion."""

from __future__ import annotations

import hashlib
import json
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select, update
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
)
from app.services.auth import audit
from app.services.documents import DocumentUpload, _safe_name, _validate_identity
from app.storage import ObjectStorage


def _key(operation: str, actor_id: uuid.UUID, client_key: str) -> str:
    return hashlib.sha256(f"{operation}\0{actor_id.hex}\0{client_key}".encode()).hexdigest()


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


def _encode_cursor(document: SharedDocument) -> str:
    payload = json.dumps(
        {"created_at": document.created_at.astimezone(UTC).isoformat(), "id": str(document.id)},
        separators=(",", ":"),
    ).encode()
    return urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        payload = json.loads(urlsafe_b64decode(value + "=" * (-len(value) % 4)))
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        if created_at.tzinfo is None:
            raise ValueError
        return created_at.astimezone(UTC), uuid.UUID(str(payload["id"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            status_code=400,
            code="invalid_request",
            message="分页游标不合法",
        ) from exc


async def _document(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    include_deleted: bool = False,
) -> SharedDocument:
    query = select(SharedDocument).where(SharedDocument.id == document_id)
    if not include_deleted:
        query = query.where(SharedDocument.deleted_at.is_(None))
    document = (await session.execute(query)).scalar_one_or_none()
    if document is None:
        raise AppError(
            status_code=404,
            code="resource_not_found",
            message="资料不存在",
        )
    return document


async def _store_document(
    session: AsyncSession,
    storage: ObjectStorage,
    user: User,
    upload: DocumentUpload,
    *,
    idempotency_key: str,
    settings: Settings,
) -> tuple[DocumentAccepted, str | None]:
    filename = _safe_name(upload.filename)
    detected_mime = _validate_identity(
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
        return (
            DocumentAccepted(
                document_id=existing.id,
                state=existing.state,
                created_at=existing.created_at,
            ),
            None,
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
        return (
            DocumentAccepted(
                document_id=existing_by_hash.id,
                state=existing_by_hash.state,
                created_at=existing_by_hash.created_at,
            ),
            None,
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
    await storage.put(document.object_key, upload.content)
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
        request_id="shared-upload",
    )
    return (
        DocumentAccepted(
            document_id=document.id,
            state=document.state,
            created_at=document.created_at,
        ),
        document.object_key,
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
    uploaded_key: str | None = None
    try:
        accepted, uploaded_key = await _store_document(
            session,
            storage,
            user,
            upload,
            idempotency_key=idempotency_key,
            settings=settings,
        )
        await session.commit()
        return accepted
    except Exception:
        await session.rollback()
        if uploaded_key is not None:
            await storage.delete(uploaded_key)
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
    uploaded_keys: list[str] = []
    try:
        for upload in uploads:
            item_key = (
                f"{idempotency_key}:{upload.filename}:{hashlib.sha256(upload.content).hexdigest()}"
            )
            item, uploaded_key = await _store_document(
                session,
                storage,
                user,
                upload,
                idempotency_key=item_key,
                settings=settings,
            )
            accepted.append(item)
            if uploaded_key is not None:
                uploaded_keys.append(uploaded_key)
        await session.commit()
    except Exception:
        await session.rollback()
        for uploaded_key in uploaded_keys:
            await storage.delete(uploaded_key)
        raise
    return DocumentBatchAccepted(
        documents=accepted,
        original_filenames=[_safe_name(upload.filename) for upload in uploads],
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
        created_at, document_id = _decode_cursor(cursor)
        query = query.where(
            or_(
                SharedDocument.created_at < created_at,
                and_(
                    SharedDocument.created_at == created_at,
                    SharedDocument.id < document_id,
                ),
            )
        )
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
        next_cursor=_encode_cursor(items[-1]) if has_more and items else None,
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
        request_id="shared-delete",
    )
    await session.commit()
