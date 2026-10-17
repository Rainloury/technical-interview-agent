"""Owner-scoped resume upload, query, retry, and source-deletion services."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import (
    AsyncJob,
    GeneratedQuestion,
    ResumeAnalysis,
    ResumeFile,
    ResumeTask,
    ResumeText,
    User,
)
from app.errors import AppError
from app.resume_processing import (
    ResumeDocument,
    extract_resume,
    sanitize_filename,
    validate_file_identity,
)
from app.schemas.resume import (
    GeneratedQuestionView,
    ResumeAccepted,
    ResumeAnalysisView,
    ResumeTaskView,
)
from app.storage import ObjectStorage

DELETED_FILENAME = "已删除简历"
DELETED_EVIDENCE_STATE = "source_deleted"
MAX_EVIDENCE_SUMMARY_CHARS = 200


@dataclass(frozen=True, slots=True)
class ResumeUpload:
    """Bounded bytes entering the private upload transaction."""

    filename: str
    declared_mime: str | None
    content: bytes


def _owner_task(task: ResumeTask | None, user: User) -> ResumeTask:
    if task is None or task.owner_user_id != user.id or task.deleted_at is not None:
        raise AppError(
            status_code=404,
            code="resource_not_found",
            message="简历任务不存在",
        )
    return task


def _fingerprint(operation: str, owner_user_id: uuid.UUID, client_key: str) -> str:
    """Hash all idempotency material without storing caller identifiers verbatim."""

    material = f"{operation}\0{owner_user_id.hex}\0{client_key}".encode()
    return hashlib.sha256(material).hexdigest()


def _idempotency_key(operation: str, owner_user_id: uuid.UUID, client_key: str) -> str:
    return f"resume:{_fingerprint(operation, owner_user_id, client_key)}"


async def _find_job(
    session: AsyncSession,
    *,
    operation: str,
    owner_user_id: uuid.UUID,
    client_key: str,
    request_fingerprint: str,
) -> AsyncJob | None:
    job = (
        await session.execute(
            select(AsyncJob).where(
                AsyncJob.idempotency_key == _idempotency_key(operation, owner_user_id, client_key)
            )
        )
    ).scalar_one_or_none()
    if job is not None and job.request_fingerprint != request_fingerprint:
        raise AppError(
            status_code=409,
            code="idempotency_conflict",
            message="该幂等键已用于其他请求",
        )
    return job


def _add_job(
    session: AsyncSession,
    *,
    operation: str,
    owner_user_id: uuid.UUID,
    client_key: str,
    request_fingerprint: str,
    job_type: str,
    resource_id: uuid.UUID,
    max_attempts: int,
) -> AsyncJob:
    job = AsyncJob(
        owner_user_id=owner_user_id,
        job_type=job_type,
        resource_type="resume_task",
        resource_id=resource_id,
        idempotency_key=_idempotency_key(operation, owner_user_id, client_key),
        request_fingerprint=request_fingerprint,
        max_attempts=max_attempts,
    )
    session.add(job)
    return job


async def _accepted(
    session: AsyncSession,
    job: AsyncJob,
    user: User,
) -> ResumeAccepted:
    task = _owner_task(await session.get(ResumeTask, job.resource_id), user)
    return ResumeAccepted(resume_task_id=task.id, state=task.state, created_at=task.created_at)


async def ensure_resume_upload_acceptable(
    *,
    filename: str,
    declared_mime: str | None,
    content: bytes,
    settings: Settings,
) -> tuple[str, ResumeDocument]:
    """Validate and extract before any object or database write occurs."""

    safe_name = sanitize_filename(filename)
    detected_mime = validate_file_identity(
        filename=safe_name,
        declared_mime=declared_mime,
        content=content,
        settings=settings,
    )
    document = extract_resume(content, detected_mime=detected_mime, settings=settings)
    return safe_name, document


async def upload_resume(
    session: AsyncSession,
    storage: ObjectStorage,
    user: User,
    upload: ResumeUpload,
    *,
    idempotency_key: str,
    settings: Settings,
) -> ResumeAccepted:
    """Validate first, then atomically enqueue one privately stored source."""

    safe_name, document = await ensure_resume_upload_acceptable(
        filename=upload.filename,
        declared_mime=upload.declared_mime,
        content=upload.content,
        settings=settings,
    )
    request_fingerprint = hashlib.sha256(
        b"\0".join(
            (
                safe_name.encode(),
                (upload.declared_mime or "").encode(),
                document.detected_mime.encode(),
                upload.content,
            )
        )
    ).hexdigest()
    existing = await _find_job(
        session,
        operation="upload",
        owner_user_id=user.id,
        client_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if existing is not None:
        return await _accepted(session, existing, user)

    object_key = f"{user.id.hex}/{uuid.uuid4().hex}"
    await storage.put(object_key, upload.content)
    now = datetime.now(UTC)
    try:
        task = ResumeTask(
            owner_user_id=user.id,
            state="uploaded",
            started_at=now,
            expires_at=now + timedelta(days=90),
        )
        session.add(task)
        await session.flush()
        session.add(
            ResumeFile(
                resume_task_id=task.id,
                owner_user_id=user.id,
                original_filename=safe_name,
                declared_mime=upload.declared_mime or "",
                detected_mime=document.detected_mime,
                size_bytes=len(upload.content),
                page_count=document.page_count,
                sha256=hashlib.sha256(upload.content).hexdigest(),
                object_key=object_key,
                storage_state="stored",
                retention_expires_at=now + timedelta(days=30),
            )
        )
        session.add(
            ResumeText(
                resume_task_id=task.id,
                owner_user_id=user.id,
                extracted_text=document.text,
                text_hash=hashlib.sha256(document.text.encode()).hexdigest(),
                extractor_version="resume-processing-v1",
                page_map={"pages": document.page_map},
                expires_at=now + timedelta(days=30),
            )
        )
        _add_job(
            session,
            operation="upload",
            owner_user_id=user.id,
            client_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            job_type="parse_resume",
            resource_id=task.id,
            max_attempts=settings.worker_max_attempts,
        )
        await session.commit()
        await session.refresh(task)
        return ResumeAccepted(
            resume_task_id=task.id,
            state=task.state,
            created_at=task.created_at,
        )
    except Exception:
        await session.rollback()
        await storage.delete(object_key)
        raise


async def get_resume_task(
    session: AsyncSession,
    user: User,
    task_id: uuid.UUID,
) -> ResumeTaskView:
    """Read one owned task without exposing private source material."""

    task = _owner_task(await session.get(ResumeTask, task_id), user)
    analysis = (
        await session.execute(
            select(ResumeAnalysis).where(
                ResumeAnalysis.resume_task_id == task.id,
                ResumeAnalysis.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    questions: list[GeneratedQuestionView] = []
    if analysis is not None:
        rows = (
            await session.execute(
                select(GeneratedQuestion)
                .where(
                    GeneratedQuestion.resume_analysis_id == analysis.id,
                    GeneratedQuestion.deleted_at.is_(None),
                )
                .order_by(GeneratedQuestion.sequence)
            )
        ).scalars()
        questions = [
            GeneratedQuestionView(
                id=question.id,
                sequence=question.sequence,
                question_text=question.question_text,
                category=question.category,
                difficulty=cast(Any, question.difficulty),
                assessment_points=question.assessment_points,
                evidence_refs=question.evidence_refs,
            )
            for question in rows
        ]
    return ResumeTaskView(
        id=task.id,
        state=cast(Any, task.state),
        failure_stage=cast(Any, task.failure_stage),
        error_code=task.error_code,
        analysis=(
            ResumeAnalysisView(
                schema_version=analysis.schema_version,
                skills=analysis.skills,
                projects=analysis.projects,
                unverified_items=analysis.unverified_items,
            )
            if analysis is not None
            else None
        ),
        questions=questions,
        created_at=task.created_at,
        completed_at=task.completed_at,
    )


async def retry_resume_task(
    session: AsyncSession,
    storage: ObjectStorage,
    user: User,
    task_id: uuid.UUID,
    *,
    idempotency_key: str,
    settings: Settings,
) -> ResumeAccepted:
    """Copy an available failed source into a new task and enqueue it."""

    original = _owner_task(await session.get(ResumeTask, task_id), user)
    if original.state != "failed":
        raise AppError(
            status_code=409,
            code="invalid_state_transition",
            message="只有失败任务可以重试",
        )
    request_fingerprint = hashlib.sha256(f"retry\0{original.id.hex}".encode()).hexdigest()
    existing = await _find_job(
        session,
        operation="retry",
        owner_user_id=user.id,
        client_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if existing is not None:
        return await _accepted(session, existing, user)

    source = (
        await session.execute(
            select(ResumeFile).where(ResumeFile.resume_task_id == original.id).with_for_update()
        )
    ).scalar_one_or_none()
    if (
        source is None
        or source.owner_user_id != user.id
        or source.storage_state != "stored"
        or source.deleted_at is not None
    ):
        raise AppError(
            status_code=409,
            code="source_unavailable",
            message="原始简历已删除，无法重试",
        )
    source_text = (
        await session.execute(
            select(ResumeText).where(
                ResumeText.resume_task_id == original.id,
                ResumeText.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if source_text is None or not source_text.extracted_text:
        raise AppError(
            status_code=409,
            code="source_unavailable",
            message="原始简历内容不可用，无法重试",
        )

    try:
        content = await storage.get(source.object_key)
    except FileNotFoundError as exc:
        raise AppError(
            status_code=409,
            code="source_unavailable",
            message="原始简历内容不可用，无法重试",
        ) from exc
    copied_key = f"{user.id.hex}/{uuid.uuid4().hex}"
    await storage.put(copied_key, content)
    now = datetime.now(UTC)
    try:
        task = ResumeTask(
            owner_user_id=user.id,
            state="uploaded",
            retry_of_task_id=original.id,
            started_at=now,
            expires_at=now + timedelta(days=90),
        )
        session.add(task)
        await session.flush()
        session.add(
            ResumeFile(
                resume_task_id=task.id,
                owner_user_id=user.id,
                original_filename=source.original_filename,
                declared_mime=source.declared_mime,
                detected_mime=source.detected_mime,
                size_bytes=source.size_bytes,
                page_count=source.page_count,
                sha256=source.sha256,
                object_key=copied_key,
                storage_state="stored",
                retention_expires_at=now + timedelta(days=30),
            )
        )
        session.add(
            ResumeText(
                resume_task_id=task.id,
                owner_user_id=user.id,
                extracted_text=source_text.extracted_text,
                text_hash=source_text.text_hash,
                extractor_version=source_text.extractor_version,
                page_map=source_text.page_map,
                expires_at=now + timedelta(days=30),
            )
        )
        _add_job(
            session,
            operation="retry",
            owner_user_id=user.id,
            client_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            job_type="parse_resume",
            resource_id=task.id,
            max_attempts=settings.worker_max_attempts,
        )
        await session.commit()
        await session.refresh(task)
        return ResumeAccepted(
            resume_task_id=task.id,
            state=task.state,
            created_at=task.created_at,
        )
    except Exception:
        await session.rollback()
        await storage.delete(copied_key)
        raise


def _redact_text(value: Any) -> Any:
    """Keep only bounded, non-locating evidence summaries."""

    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key in {
                "page",
                "pages",
                "start",
                "end",
                "section",
                "char_start",
                "char_end",
                "filename",
                "original_filename",
                "object_key",
            }:
                continue
            if key in {"summary", "quote", "evidence"} and isinstance(item, str):
                redacted[key] = item[:MAX_EVIDENCE_SUMMARY_CHARS]
            else:
                redacted[key] = _redact_text(item)
        redacted["source_state"] = DELETED_EVIDENCE_STATE
        return redacted
    if isinstance(value, list):
        return [_redact_text(item) for item in value]
    if isinstance(value, str):
        return value[:MAX_EVIDENCE_SUMMARY_CHARS]
    return value


async def delete_resume_source(
    session: AsyncSession,
    storage: ObjectStorage,
    user: User,
    task_id: uuid.UUID,
    *,
    idempotency_key: str,
    settings: Settings,
) -> None:
    """Commit an irreversible tombstone before deleting the private object."""

    task = _owner_task(await session.get(ResumeTask, task_id), user)
    operation_fingerprint = hashlib.sha256(f"delete-source\0{task.id.hex}".encode()).hexdigest()
    existing = await _find_job(
        session,
        operation="delete-source",
        owner_user_id=user.id,
        client_key=idempotency_key,
        request_fingerprint=operation_fingerprint,
    )
    if existing is not None and existing.state in {"queued", "leased", "succeeded"}:
        return None
    if task.state == "source_deleted":
        return None

    source = (
        await session.execute(
            select(ResumeFile).where(ResumeFile.resume_task_id == task.id).with_for_update()
        )
    ).scalar_one_or_none()
    if source is None:
        raise AppError(status_code=404, code="resource_not_found", message="简历任务不存在")
    now = datetime.now(UTC)
    source.storage_state = "delete_pending"
    source.original_filename = DELETED_FILENAME
    task.state = "source_deleted"
    text = (
        await session.execute(select(ResumeText).where(ResumeText.resume_task_id == task.id))
    ).scalar_one_or_none()
    if text is not None:
        text.extracted_text = ""
        text.page_map = {"source_state": DELETED_EVIDENCE_STATE}
        text.deleted_at = now
    analyses = (
        await session.execute(
            select(ResumeAnalysis).where(ResumeAnalysis.resume_task_id == task.id)
        )
    ).scalars()
    analysis_ids: list[uuid.UUID] = []
    for analysis in analyses:
        analysis.skills = _redact_text(analysis.skills)
        analysis.projects = _redact_text(analysis.projects)
        analysis.evidence = _redact_text(analysis.evidence)
        analysis.unverified_items = _redact_text(analysis.unverified_items)
        analysis.gaps = _redact_text(analysis.gaps)
        analysis_ids.append(analysis.id)
    if analysis_ids:
        questions = (
            await session.execute(
                select(GeneratedQuestion).where(
                    GeneratedQuestion.resume_analysis_id.in_(analysis_ids)
                )
            )
        ).scalars()
        for question in questions:
            question.assessment_points = _redact_text(question.assessment_points)
            question.evidence_refs = _redact_text(question.evidence_refs)
            question.reference_answer = ""
            question.scoring_rubric = {"source_state": DELETED_EVIDENCE_STATE}
    _add_job(
        session,
        operation="delete-source",
        owner_user_id=user.id,
        client_key=idempotency_key,
        request_fingerprint=operation_fingerprint,
        job_type="delete_data",
        resource_id=task.id,
        max_attempts=settings.worker_max_attempts,
    )
    await session.commit()

    try:
        await storage.delete(source.object_key)
    except Exception:
        async with session.begin():
            persisted = await session.get(ResumeFile, source.id)
            if persisted is not None:
                persisted.storage_state = "delete_failed"
        return None
    async with session.begin():
        persisted = await session.get(ResumeFile, source.id)
        if persisted is not None:
            persisted.storage_state = "deleted"
            persisted.deleted_at = now
