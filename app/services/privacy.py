"""Owner-scoped privacy requests, visibility tombstones, and deletion status."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.jobs import enqueue_job
from app.db.models import (
    DataDeletionRequest,
    Interview,
    QaEvidence,
    QaRequest,
    ResumeFile,
    ResumeTask,
    User,
    UserDocument,
    UserDocumentChunk,
    WrongQuestion,
)
from app.errors import AppError
from app.schemas.privacy import DataDeletionAccepted, DataDeletionStatus

DELETION_SCOPES = (
    "resume_tasks",
    "qa_requests",
    "interviews",
    "wrong_questions",
    "weak_points",
    "user_documents",
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _status(request: DataDeletionRequest) -> DataDeletionStatus:
    return DataDeletionStatus(
        request_id=request.id,
        state=cast(Any, request.state),
        scope=[value for value in request.scope.get("items", []) if isinstance(value, str)],
        result=request.result,
        error_code=request.error_code,
        created_at=request.created_at,
        updated_at=request.updated_at,
        completed_at=request.completed_at,
    )


async def latest_deletion_status(
    session: AsyncSession,
    user: User,
) -> DataDeletionStatus | None:
    """Return the newest deletion request without exposing another owner's data."""

    request = (
        await session.execute(
            select(DataDeletionRequest)
            .where(DataDeletionRequest.owner_user_id == user.id)
            .order_by(DataDeletionRequest.created_at.desc(), DataDeletionRequest.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return _status(request) if request is not None else None


async def request_data_deletion(
    session: AsyncSession,
    user: User,
    *,
    idempotency_key: str,
    settings: Settings,
) -> DataDeletionAccepted:
    """Tombstone visible business data, then enqueue private cleanup."""

    key = _hash(f"delete-account-data\0{user.id.hex}\0{idempotency_key}")
    fingerprint = _hash(f"delete-account-data\0{user.id.hex}")
    existing = (
        await session.execute(
            select(DataDeletionRequest).where(
                DataDeletionRequest.owner_user_id == user.id,
                DataDeletionRequest.idempotency_key == key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise AppError(
                status_code=409,
                code="idempotency_conflict",
                message="该幂等键已用于其他删除请求",
            )
        return DataDeletionAccepted(
            request_id=existing.id,
            state="requested",
            accepted_at=existing.created_at,
        )

    now = datetime.now(UTC)
    request = DataDeletionRequest(
        owner_user_id=user.id,
        idempotency_key=key,
        request_fingerprint=fingerprint,
        state="requested",
        scope={"items": list(DELETION_SCOPES)},
    )
    session.add(request)
    await session.flush()

    # Make all business records invisible in the same transaction as the
    # deletion request before any asynchronous object cleanup starts.
    resume_tasks = list(
        (
            await session.execute(
                select(ResumeTask)
                .where(ResumeTask.owner_user_id == user.id, ResumeTask.deleted_at.is_(None))
                .with_for_update()
            )
        ).scalars()
    )
    for task in resume_tasks:
        task.deleted_at = now
    sources = list(
        (
            await session.execute(
                select(ResumeFile)
                .where(ResumeFile.owner_user_id == user.id, ResumeFile.deleted_at.is_(None))
                .with_for_update()
            )
        ).scalars()
    )
    for source in sources:
        source.storage_state = "delete_pending"

    qa_requests = list(
        (
            await session.execute(
                select(QaRequest)
                .where(QaRequest.owner_user_id == user.id, QaRequest.deleted_at.is_(None))
                .with_for_update()
            )
        ).scalars()
    )
    for request_row in qa_requests:
        request_row.deleted_at = now

    interviews = list(
        (
            await session.execute(
                select(Interview)
                .where(Interview.owner_user_id == user.id, Interview.deleted_at.is_(None))
                .with_for_update()
            )
        ).scalars()
    )
    for interview in interviews:
        interview.deleted_at = now

    questions = list(
        (
            await session.execute(
                select(WrongQuestion)
                .where(
                    WrongQuestion.owner_user_id == user.id,
                    WrongQuestion.deleted_at.is_(None),
                )
                .with_for_update()
            )
        ).scalars()
    )
    for question in questions:
        question.deleted_at = now

    documents = list(
        (
            await session.execute(
                select(UserDocument)
                .where(
                    UserDocument.owner_user_id == user.id,
                    UserDocument.deleted_at.is_(None),
                )
                .with_for_update()
            )
        ).scalars()
    )
    for document in documents:
        document.state = "deleted"
        document.deletion_state = "pending"
        document.deleted_at = now
        document.updated_at = now
    document_ids = [document.id for document in documents]
    if document_ids:
        chunk_ids = select(UserDocumentChunk.id).where(
            UserDocumentChunk.document_id.in_(document_ids)
        )
        await session.execute(
            update(QaEvidence)
            .where(QaEvidence.user_document_chunk_id.in_(chunk_ids))
            .values(source_state="source_deleted")
        )

    await enqueue_job(
        session,
        owner_user_id=user.id,
        job_type="delete_account_data",
        resource_type="data_deletion_request",
        resource_id=request.id,
        idempotency_key=f"delete-account-data:{request.id}",
        max_attempts=settings.worker_max_attempts,
        request_fingerprint=fingerprint,
    )
    await session.commit()
    return DataDeletionAccepted(
        request_id=request.id,
        state="requested",
        accepted_at=request.created_at,
    )


async def get_deletion_status(
    session: AsyncSession,
    user: User,
    request_id: uuid.UUID,
) -> DataDeletionStatus:
    request = (
        await session.execute(
            select(DataDeletionRequest).where(
                DataDeletionRequest.id == request_id,
                DataDeletionRequest.owner_user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if request is None:
        raise AppError(
            status_code=404,
            code="resource_not_found",
            message="删除请求不存在",
        )
    return _status(request)


def next_retention_run(now: datetime | None = None) -> datetime:
    """Return the next daily retention sweep time."""

    current = now or datetime.now(UTC)
    return current + timedelta(days=1)
