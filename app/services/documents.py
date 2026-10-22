"""Owner-scoped private document upload, listing, detail, and deletion."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import filetype
from sqlalchemy import and_, or_, select, update
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
)
from app.storage import ObjectStorage

SUPPORTED_MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


@dataclass(frozen=True, slots=True)
class DocumentUpload:
    """Bounded bytes entering the private document transaction."""

    filename: str
    declared_mime: str | None
    content: bytes
    title: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentCursor:
    """Stable list cursor using created_at and UUID."""

    created_at: datetime
    id: uuid.UUID


def _key(operation: str, owner_id: uuid.UUID, client_key: str) -> str:
    material = f"{operation}\0{owner_id.hex}\0{client_key}".encode()
    return hashlib.sha256(material).hexdigest()


def _safe_name(filename: str) -> str:
    name = Path(filename or "").name.strip()
    name = "".join(char for char in name if char.isprintable())
    if not name:
        raise AppError(
            status_code=422,
            code="unsupported_source",
            message="请选择支持的资料文件",
        )
    return name[:255]


def _validate_identity(
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
        retention_expires_at=document.retention_expires_at,
    )


def _encode_cursor(document: UserDocument) -> str:
    payload = json.dumps(
        {"created_at": document.created_at.astimezone(UTC).isoformat(), "id": str(document.id)},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str) -> DocumentCursor:
    try:
        payload = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        if created_at.tzinfo is None:
            raise ValueError
        return DocumentCursor(
            created_at=created_at.astimezone(UTC),
            id=uuid.UUID(str(payload["id"])),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            status_code=400,
            code="invalid_request",
            message="分页游标不合法",
        ) from exc


async def _owned_document(
    session: AsyncSession,
    user: User,
    document_id: uuid.UUID,
    *,
    include_deleted: bool = False,
) -> UserDocument:
    query = select(UserDocument).where(
        UserDocument.id == document_id,
        UserDocument.owner_user_id == user.id,
    )
    if not include_deleted:
        query = query.where(UserDocument.deleted_at.is_(None))
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
    """Validate, privately store, and enqueue one document without committing."""

    filename = _safe_name(upload.filename)
    detected_mime = _validate_identity(
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
        return (
            DocumentAccepted(
                document_id=existing_document.id,
                state=existing_document.state,
                created_at=existing_document.created_at,
            ),
            None,
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
        return (
            DocumentAccepted(
                document_id=existing_by_key.id,
                state=existing_by_key.state,
                created_at=existing_by_key.created_at,
            ),
            None,
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
    uploaded_object: str | None = None
    if stored_document is not None and stored_document.state in {"uploaded", "processing", "ready"}:
        return (
            DocumentAccepted(
                document_id=stored_document.id,
                state=stored_document.state,
                created_at=stored_document.created_at,
            ),
            None,
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
        await storage.put(object_key, upload.content)
        uploaded_object = object_key
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
        await storage.put(document.object_key, upload.content)
        uploaded_object = document.object_key
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
    return (
        DocumentAccepted(
            document_id=document.id,
            state=document.state,
            created_at=document.created_at,
        ),
        uploaded_object,
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
    """Validate, privately store, enqueue, and commit one document."""

    uploaded_object: str | None = None
    try:
        accepted, uploaded_object = await _store_document(
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
        if uploaded_object is not None:
            await storage.delete(uploaded_object)
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
    """Store and enqueue every file in one atomic batch."""

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
    accepted: list[DocumentAccepted] = []
    uploaded_objects: list[str] = []
    try:
        for upload in uploads:
            content_hash = hashlib.sha256(upload.content).hexdigest()
            item_key = f"{idempotency_key}:{upload.filename}:{content_hash}"
            accepted_item, uploaded_object = await _store_document(
                session,
                storage,
                user,
                upload,
                idempotency_key=item_key,
                settings=settings,
            )
            accepted.append(accepted_item)
            if uploaded_object is not None:
                uploaded_objects.append(uploaded_object)
        await session.commit()
    except Exception:
        await session.rollback()
        for object_key in uploaded_objects:
            await storage.delete(object_key)
        raise
    return DocumentBatchAccepted(
        documents=accepted,
        original_filenames=[_safe_name(upload.filename) for upload in uploads],
    )


async def list_documents(
    session: AsyncSession,
    user: User,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> DocumentPage:
    """Return a stable owner-scoped document page."""

    now = datetime.now(UTC)
    query = select(UserDocument).where(
        UserDocument.owner_user_id == user.id,
        UserDocument.deleted_at.is_(None),
        UserDocument.retention_expires_at > now,
    )
    if cursor:
        parsed = _decode_cursor(cursor)
        query = query.where(
            or_(
                UserDocument.created_at < parsed.created_at,
                and_(UserDocument.created_at == parsed.created_at, UserDocument.id < parsed.id),
            )
        )
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
        next_cursor=_encode_cursor(items[-1]) if has_more and items else None,
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
    """Tombstone a document immediately and enqueue private cleanup."""

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
