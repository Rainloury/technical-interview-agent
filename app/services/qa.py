"""Owner-scoped retrieval QA creation, replay, evidence, and event persistence."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import (
    AsyncJob,
    QaEvidence,
    QaRequest,
    QaStreamEvent,
    User,
)
from app.errors import AppError
from app.qa_contracts import QaAnswerOutput, contains_url
from app.schemas.qa import (
    QaAccepted,
    QaAnswerView,
    QaCreate,
    QaEvidenceView,
    QaRequestView,
)

QA_MODEL_NAME = "DEFAULT"
QA_PROMPT_VERSION = "1.0.0"


def _idempotency_key(owner_user_id: uuid.UUID, client_key: str) -> str:
    material = f"qa\0{owner_user_id.hex}\0{client_key}".encode()
    return hashlib.sha256(material).hexdigest()


def _raise_unsupported_source() -> None:
    raise AppError(
        status_code=422,
        code="unsupported_source",
        message="问题中不能包含 URL，检索只使用已审核知识源",
    )


def validate_question_input(payload: QaCreate) -> str:
    """Normalize bounded text and reject caller-controlled source locations."""

    question = " ".join(payload.question.split())
    if contains_url(question):
        _raise_unsupported_source()
    return question


async def _owned_request(
    session: AsyncSession,
    user: User,
    request_id: uuid.UUID,
    *,
    lock: bool = False,
) -> QaRequest:
    statement = select(QaRequest).where(
        QaRequest.id == request_id,
        QaRequest.owner_user_id == user.id,
        QaRequest.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    request = (await session.execute(statement)).scalar_one_or_none()
    if request is None:
        raise AppError(
            status_code=404,
            code="resource_not_found",
            message="问答记录不存在",
        )
    return request


async def append_event(
    session: AsyncSession,
    request: QaRequest,
    *,
    event_type: str,
    payload: dict[str, Any],
) -> QaStreamEvent:
    """Allocate one durable sequence number while the owning request row is locked."""

    if event_type not in {"started", "delta", "evidence", "completed", "error"}:
        raise ValueError("unsupported QA event type")
    terminal_event = (
        await session.execute(
            select(QaStreamEvent)
            .where(
                QaStreamEvent.qa_request_id == request.id,
                QaStreamEvent.event_type.in_(("completed", "error")),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if event_type in {"completed", "error"} and terminal_event is not None:
        raise ValueError("terminal QA event already exists")
    if request.state in {"completed", "failed"} and event_type not in {"completed", "error"}:
        raise ValueError("terminal QA requests cannot append progress events")
    if event_type == "completed" and request.answer_json is None:
        raise ValueError("completed QA event requires a persisted answer")
    if event_type == "completed" and request.state != "completed":
        raise ValueError("completed QA event requires completed request state")
    if event_type == "error" and request.state != "failed":
        raise ValueError("error QA event requires failed request state")
    seq = request.last_event_seq + 1
    event = QaStreamEvent(
        qa_request_id=request.id,
        seq=seq,
        event_type=event_type,
        payload_json=payload,
    )
    session.add(event)
    request.last_event_seq = seq
    await session.flush()
    return event


async def create_qa_request(
    session: AsyncSession,
    user: User,
    payload: QaCreate,
    *,
    idempotency_key: str,
    settings: Settings,
) -> QaAccepted:
    """Validate first, then atomically create one request, stream start, and job."""

    question = validate_question_input(payload)
    key = _idempotency_key(user.id, idempotency_key)
    existing = (
        await session.execute(
            select(QaRequest).where(
                QaRequest.owner_user_id == user.id,
                QaRequest.idempotency_key == key,
                QaRequest.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if (
            existing.question_text != question
            or existing.answer_preference != payload.answer_preference
        ):
            raise AppError(
                status_code=409,
                code="idempotency_conflict",
                message="该幂等键已用于其他问答请求",
            )
        return QaAccepted(
            qa_request_id=existing.id,
            stream_url=f"/api/v1/qa/{existing.id}/stream",
            state=cast(Any, existing.state),
        )

    now = datetime.now(UTC)
    request = QaRequest(
        owner_user_id=user.id,
        question_text=question,
        answer_preference=payload.answer_preference,
        idempotency_key=key,
        state="created",
        model_name=QA_MODEL_NAME,
        prompt_version=QA_PROMPT_VERSION,
        expires_at=now + timedelta(days=90),
    )
    session.add(request)
    try:
        await session.flush()
        await append_event(
            session,
            request,
            event_type="started",
            payload={"request_id": str(request.id)},
        )
        session.add(
            AsyncJob(
                owner_user_id=user.id,
                job_type="answer_question",
                resource_type="qa_request",
                resource_id=request.id,
                idempotency_key=f"qa:{key}",
                request_fingerprint=hashlib.sha256(
                    f"{question}\0{payload.answer_preference}".encode()
                ).hexdigest(),
                max_attempts=settings.worker_max_attempts,
            )
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        replay = (
            await session.execute(
                select(QaRequest).where(
                    QaRequest.owner_user_id == user.id,
                    QaRequest.idempotency_key == key,
                    QaRequest.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if replay is None:
            raise
        if (
            replay.question_text != question
            or replay.answer_preference != payload.answer_preference
        ):
            raise AppError(
                status_code=409,
                code="idempotency_conflict",
                message="该幂等键已用于其他问答请求",
            ) from None
        return QaAccepted(
            qa_request_id=replay.id,
            stream_url=f"/api/v1/qa/{replay.id}/stream",
            state=cast(Any, replay.state),
        )
    await session.refresh(request)
    return QaAccepted(
        qa_request_id=request.id,
        stream_url=f"/api/v1/qa/{request.id}/stream",
        state=cast(Any, request.state),
    )


def _citation_id(evidence: QaEvidence, fallback_index: int) -> str:
    if isinstance(evidence.position, dict):
        value = evidence.position.get("citation_id")
        if isinstance(value, str) and value:
            return value
    return f"evidence-{fallback_index}"


async def evidence_for_request(
    session: AsyncSession,
    request_id: uuid.UUID,
) -> list[QaEvidence]:
    return list(
        (
            await session.execute(
                select(QaEvidence)
                .where(QaEvidence.qa_request_id == request_id)
                .order_by(
                    QaEvidence.position["rank"].as_integer(),
                    QaEvidence.created_at,
                    QaEvidence.id,
                )
            )
        ).scalars()
    )


def public_evidence(rows: list[QaEvidence]) -> list[QaEvidenceView]:
    """Map internal frozen rows to non-locating public proof."""

    return [
        QaEvidenceView(
            citation_id=_citation_id(row, index),
            title=row.source_title,
            section_path=row.section_path,
            snippet=row.snippet[:200],
            relevance_score=float(row.relevance_score),
            source_state=cast(Any, row.source_state),
        )
        for index, row in enumerate(rows, start=1)
    ]


async def _error_event(
    session: AsyncSession,
    request_id: uuid.UUID,
) -> tuple[dict[str, Any] | None, bool]:
    event = (
        await session.execute(
            select(QaStreamEvent)
            .where(
                QaStreamEvent.qa_request_id == request_id,
                QaStreamEvent.event_type == "error",
            )
            .order_by(QaStreamEvent.seq.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if event is None:
        return None, False
    payload = event.payload_json
    retryable = bool(payload.get("retryable", False))
    return payload, retryable


async def get_qa_request(
    session: AsyncSession,
    user: User,
    request_id: uuid.UUID,
) -> QaRequestView:
    """Return only owner-visible state, final answer, and public evidence."""

    request = await _owned_request(session, user, request_id)
    evidence = await evidence_for_request(session, request.id)
    answer = (
        QaAnswerView.model_validate(request.answer_json)
        if request.answer_json is not None
        else None
    )
    error, _ = await _error_event(session, request.id)
    return QaRequestView(
        id=request.id,
        question=request.question_text,
        answer_preference=cast(Any, request.answer_preference),
        state=cast(Any, request.state),
        answer=answer,
        evidence=public_evidence(evidence),
        evidence_status=cast(Any, request.evidence_status),
        error=error,
        created_at=request.created_at,
        completed_at=request.completed_at,
        last_event_seq=request.last_event_seq,
    )


async def assert_stream_owner(
    session: AsyncSession,
    user: User,
    request_id: uuid.UUID,
) -> None:
    await _owned_request(session, user, request_id)


async def events_after(
    session: AsyncSession,
    request_id: uuid.UUID,
    *,
    after_seq: int,
) -> tuple[list[QaStreamEvent], bool]:
    request = await session.get(QaRequest, request_id)
    if request is None:
        return [], True
    events = list(
        (
            await session.execute(
                select(QaStreamEvent)
                .where(
                    QaStreamEvent.qa_request_id == request_id,
                    QaStreamEvent.seq > after_seq,
                )
                .order_by(QaStreamEvent.seq)
            )
        ).scalars()
    )
    terminal = request.state in {"completed", "failed"}
    return events, terminal


def apply_answer(
    request: QaRequest,
    output: QaAnswerOutput,
    *,
    prompt_version: str,
) -> None:
    """Persist the validated answer before the completion event is appended."""

    now = datetime.now(UTC)
    request.answer_json = output.model_dump(mode="json")
    request.evidence_status = output.evidence_status
    request.extended_questions = {"items": output.extended_questions}
    request.prompt_version = prompt_version
    request.state = "completed"
    request.completed_at = now


def completion_payload(
    request: QaRequest,
    evidence: list[QaEvidence],
) -> dict[str, Any]:
    """Build the final SSE payload from persisted answer and frozen proof."""

    if request.answer_json is None:
        raise ValueError("completed QA request is missing its answer")
    return {
        "answer": request.answer_json,
        "evidence": [item.model_dump(mode="json") for item in public_evidence(evidence)],
        "extended_questions": request.answer_json.get("extended_questions", []),
    }
