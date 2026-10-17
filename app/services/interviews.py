"""Owner-scoped interview lifecycle, idempotent operations, and reports."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.jobs import enqueue_job
from app.db.models import (
    FollowUpChain,
    Interview,
    InterviewOperation,
    InterviewReport,
    InterviewTurn,
    User,
    WeakPoint,
    WeakPointEvidence,
    WrongQuestion,
)
from app.errors import AppError
from app.interview_contracts import (
    INTERVIEW_BLUEPRINT_VERSION,
    INTERVIEW_DURATION_SECONDS,
    INTERVIEW_MAIN_QUESTION_COUNT,
    INTERVIEW_SCORING_VERSION,
    INTERVIEW_TOTAL_TOKEN_BUDGET,
    build_blueprint,
    normalize_topic_keys,
)
from app.schemas.interview import (
    InterviewBranchAction,
    InterviewConfigurationView,
    InterviewCreate,
    InterviewCreated,
    InterviewProgress,
    InterviewReportTurn,
    InterviewReportView,
    InterviewStartView,
    InterviewTurnAccepted,
    InterviewTurnView,
    InterviewView,
    WeakPointEvidenceView,
    WeakPointPage,
    WeakPointSummary,
    WrongQuestionDetail,
    WrongQuestionPage,
    WrongQuestionSummary,
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _operation_key(owner_user_id: uuid.UUID, client_key: str) -> str:
    return _hash(f"interview-operation\0{owner_user_id.hex}\0{client_key}")


def _answer_key(owner_user_id: uuid.UUID, interview_id: uuid.UUID, client_key: str) -> str:
    return _hash(f"interview-answer\0{owner_user_id.hex}\0{interview_id.hex}\0{client_key}")


def _fingerprint(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def database_now(session: AsyncSession) -> datetime:
    value = (await session.execute(select(func.statement_timestamp()))).scalar_one()
    return cast(datetime, value)


def _configuration(interview: Interview) -> InterviewConfigurationView:
    difficulty = interview.difficulty_profile.get("difficulty", "balanced")
    topics = interview.topic_keys.get("selected", [])
    return InterviewConfigurationView(
        direction=cast(Any, interview.direction),
        difficulty=cast(Any, difficulty),
        topic_keys=[value for value in topics if isinstance(value, str)],
    )


async def _owned_interview(
    session: AsyncSession,
    user: User,
    interview_id: uuid.UUID,
    *,
    lock: bool = False,
) -> Interview:
    statement = select(Interview).where(
        Interview.id == interview_id,
        Interview.owner_user_id == user.id,
        Interview.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    interview = (await session.execute(statement)).scalar_one_or_none()
    if interview is None:
        raise AppError(
            status_code=404,
            code="resource_not_found",
            message="面试记录不存在",
        )
    return interview


async def _owned_turn(
    session: AsyncSession,
    user: User,
    interview_id: uuid.UUID,
    turn_id: uuid.UUID,
    *,
    lock: bool = False,
) -> InterviewTurn:
    statement = select(InterviewTurn).where(
        InterviewTurn.id == turn_id,
        InterviewTurn.interview_id == interview_id,
        InterviewTurn.owner_user_id == user.id,
    )
    if lock:
        statement = statement.with_for_update()
    turn = (await session.execute(statement)).scalar_one_or_none()
    if turn is None:
        raise AppError(
            status_code=404,
            code="resource_not_found",
            message="面试轮次不存在",
        )
    return turn


def _remaining_seconds(deadline_at: datetime | None, now: datetime) -> int:
    if deadline_at is None:
        return INTERVIEW_DURATION_SECONDS
    return max(0, int((deadline_at - now).total_seconds()))


async def _progress(
    session: AsyncSession,
    interview: Interview,
    now: datetime,
) -> InterviewProgress:
    turns = list(
        (
            await session.execute(
                select(InterviewTurn).where(
                    InterviewTurn.interview_id == interview.id,
                    InterviewTurn.owner_user_id == interview.owner_user_id,
                )
            )
        ).scalars()
    )
    completed_roots = {
        turn.root_turn_id
        for turn in turns
        if turn.turn_type == "main" and turn.state in {"passed", "failed", "scoring_failed"}
    }
    chain = next(
        (
            item
            for item in (
                await session.execute(
                    select(FollowUpChain).where(FollowUpChain.interview_id == interview.id)
                )
            ).scalars()
        ),
        None,
    )
    chain_state: str | None = None
    if chain is not None:
        chain_state = chain.state
    elif any(turn.state == "scoring" for turn in turns):
        chain_state = "scoring"
    elif any(turn.state == "awaiting_answer" for turn in turns):
        chain_state = "awaiting_answer"
    total = interview.main_question_count
    completed = min(total, len(completed_roots))
    return InterviewProgress(
        main_questions_completed=completed,
        main_questions_total=total,
        main_questions_remaining=max(0, total - completed),
        current_follow_up_chain=cast(Any, chain_state),
        remaining_seconds=_remaining_seconds(interview.deadline_at, now),
    )


async def _active_turn(
    session: AsyncSession,
    interview_id: uuid.UUID,
) -> InterviewTurn | None:
    return (
        await session.execute(
            select(InterviewTurn)
            .where(
                InterviewTurn.interview_id == interview_id,
                InterviewTurn.state.in_(("awaiting_answer", "scoring", "pending")),
            )
            .order_by(
                func.array_position(
                    text("ARRAY['awaiting_answer','scoring','pending']"),
                    InterviewTurn.state,
                ),
                InterviewTurn.sequence,
            )
            .limit(1)
        )
    ).scalar_one_or_none()


def _public_turn(turn: InterviewTurn) -> InterviewTurnView:
    return InterviewTurnView(
        id=turn.id,
        type=cast(Any, turn.turn_type),
        depth=turn.depth,
        question_text=turn.question_text,
        topic_key=turn.topic_key,
        difficulty=cast(Any, turn.difficulty),
        state=cast(Any, turn.state),
    )


async def _public_view(
    session: AsyncSession,
    interview: Interview,
    now: datetime,
) -> InterviewView:
    active = await _active_turn(session, interview.id)
    submitted = list(
        (
            await session.execute(
                select(InterviewTurn)
                .where(
                    InterviewTurn.interview_id == interview.id,
                    InterviewTurn.submitted_at.is_not(None),
                )
                .order_by(InterviewTurn.sequence)
            )
        ).scalars()
    )
    return InterviewView(
        interview_id=interview.id,
        state=cast(Any, interview.state),
        direction=cast(Any, interview.direction),
        configuration=_configuration(interview),
        server_time=now,
        deadline_at=interview.deadline_at,
        ended_at=interview.ended_at,
        current_turn=_public_turn(active) if active is not None else None,
        submitted_turns=[_public_turn(turn) for turn in submitted],
        progress=await _progress(session, interview, now),
    )


async def _operation_replay(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    interview_id: uuid.UUID,
    operation: str,
    key: str,
    fingerprint: str,
) -> dict[str, Any] | None:
    record = (
        await session.execute(
            select(InterviewOperation).where(
                InterviewOperation.owner_user_id == owner_user_id,
                InterviewOperation.interview_id == interview_id,
                InterviewOperation.operation == operation,
                InterviewOperation.idempotency_key == key,
            )
        )
    ).scalar_one_or_none()
    if record is None:
        return None
    if record.request_fingerprint != fingerprint:
        raise AppError(
            status_code=409,
            code="idempotency_conflict",
            message="该幂等键已用于其他操作",
        )
    return record.response_json


def _store_operation(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    interview_id: uuid.UUID,
    operation: str,
    key: str,
    fingerprint: str,
    response: dict[str, Any],
) -> None:
    session.add(
        InterviewOperation(
            owner_user_id=owner_user_id,
            interview_id=interview_id,
            operation=operation,
            idempotency_key=key,
            request_fingerprint=fingerprint,
            response_json=response,
        )
    )


async def create_interview(
    session: AsyncSession,
    user: User,
    payload: InterviewCreate,
    *,
    idempotency_key: str,
    settings: Settings,
) -> InterviewCreated:
    """Create a frozen configuration and an internal blueprint in one transaction."""

    try:
        selected = normalize_topic_keys(payload.direction, payload.topic_keys)
    except ValueError as exc:
        raise AppError(status_code=422, code="invalid_request", message=str(exc)) from exc
    key = _operation_key(user.id, idempotency_key)
    fingerprint = _fingerprint(payload.model_dump(mode="json"))
    existing = (
        await session.execute(
            select(Interview).where(
                Interview.owner_user_id == user.id,
                Interview.blueprint_version == f"{INTERVIEW_BLUEPRINT_VERSION}:{key}",
                Interview.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        stored = existing.topic_keys.get("request_fingerprint")
        if stored != fingerprint:
            raise AppError(
                status_code=409,
                code="idempotency_conflict",
                message="该幂等键已用于其他面试配置",
            )
        return InterviewCreated(
            interview_id=existing.id,
            state=cast(Any, existing.state),
            main_question_count=existing.main_question_count,
            deadline_at=existing.deadline_at,
            configuration=_configuration(existing),
        )

    now = await database_now(session)
    interview = Interview(
        owner_user_id=user.id,
        direction=payload.direction,
        difficulty_profile={"difficulty": payload.difficulty},
        topic_keys={
            "selected": selected,
            "request_fingerprint": fingerprint,
        },
        state="created",
        main_question_count=INTERVIEW_MAIN_QUESTION_COUNT,
        total_token_budget=INTERVIEW_TOTAL_TOKEN_BUDGET,
        blueprint_version=f"{INTERVIEW_BLUEPRINT_VERSION}:{key}",
        scoring_version=INTERVIEW_SCORING_VERSION,
        expires_at=now + timedelta(days=90),
    )
    session.add(interview)
    await session.flush()
    blueprint = build_blueprint(
        direction=payload.direction,
        difficulty=payload.difficulty,
        topic_keys=selected,
        interview_id=str(interview.id),
    )
    interview.topic_keys = {
        **interview.topic_keys,
        "blueprint": [
            {
                "sequence": item.sequence,
                "topic_key": item.topic_key,
                "topic_title": item.topic_title,
                "capability": item.capability,
                "difficulty": item.difficulty,
                "anchors": list(item.anchors),
                "seed": item.seed,
            }
            for item in blueprint
        ],
    }
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = (
            await session.execute(
                select(Interview).where(
                    Interview.owner_user_id == user.id,
                    Interview.blueprint_version == f"{INTERVIEW_BLUEPRINT_VERSION}:{key}",
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        if existing.topic_keys.get("request_fingerprint") != fingerprint:
            raise AppError(
                status_code=409,
                code="idempotency_conflict",
                message="该幂等键已用于其他面试配置",
            ) from None
        return InterviewCreated(
            interview_id=existing.id,
            state=cast(Any, existing.state),
            main_question_count=existing.main_question_count,
            deadline_at=existing.deadline_at,
            configuration=_configuration(existing),
        )
    await session.refresh(interview)
    return InterviewCreated(
        interview_id=interview.id,
        state=cast(Any, interview.state),
        main_question_count=interview.main_question_count,
        deadline_at=interview.deadline_at,
        configuration=_configuration(interview),
    )


async def start_interview(
    session: AsyncSession,
    user: User,
    interview_id: uuid.UUID,
    *,
    idempotency_key: str,
    settings: Settings,
) -> InterviewStartView:
    """Freeze the server deadline exactly once and enqueue root question generation."""

    interview = await _owned_interview(session, user, interview_id, lock=True)
    key = _operation_key(user.id, idempotency_key)
    fingerprint = _fingerprint({"operation": "start"})
    replay = await _operation_replay(
        session,
        owner_user_id=user.id,
        interview_id=interview.id,
        operation="start",
        key=key,
        fingerprint=fingerprint,
    )
    if replay is not None:
        return InterviewStartView.model_validate(replay)
    if interview.state in {"completed", "timed_out", "cancelled", "failed"}:
        raise AppError(
            status_code=409,
            code="invalid_state_transition",
            message="该面试已经结束",
        )
    now = await database_now(session)
    if interview.state == "created":
        await session.execute(
            text(
                "UPDATE interviews "
                "SET state = 'in_progress', "
                "started_at = statement_timestamp(), "
                "deadline_at = statement_timestamp() + make_interval(secs => :duration) "
                "WHERE id = :interview_id"
            ),
            {
                "duration": INTERVIEW_DURATION_SECONDS,
                "interview_id": interview.id,
            },
        )
        await session.refresh(interview)
        now = await database_now(session)
        await enqueue_job(
            session,
            owner_user_id=user.id,
            job_type="score_open_interview_turn",
            resource_type="interview",
            resource_id=interview.id,
            idempotency_key=f"interview-open:{interview.id}",
            request_fingerprint=fingerprint,
            max_attempts=settings.worker_max_attempts,
        )
    current = await _active_turn(session, interview.id)
    view = InterviewStartView(
        interview_id=interview.id,
        state=cast(Any, interview.state),
        server_time=now,
        deadline_at=interview.deadline_at,
        current_turn=_public_turn(current) if current is not None else None,
        progress=await _progress(session, interview, now),
    )
    _store_operation(
        session,
        owner_user_id=user.id,
        interview_id=interview.id,
        operation="start",
        key=key,
        fingerprint=fingerprint,
        response=view.model_dump(mode="json"),
    )
    await session.commit()
    return view


async def get_interview(
    session: AsyncSession,
    user: User,
    interview_id: uuid.UUID,
) -> InterviewView:
    interview = await _owned_interview(session, user, interview_id)
    now = await database_now(session)
    if (
        interview.state == "in_progress"
        and interview.deadline_at is not None
        and now >= interview.deadline_at
    ):
        await _timeout_interview(session, interview, now)
        await session.commit()
    return await _public_view(session, interview, now)


async def submit_answer(
    session: AsyncSession,
    user: User,
    interview_id: uuid.UUID,
    turn_id: uuid.UUID,
    *,
    answer: str,
    client_submitted_at: datetime | None,
    idempotency_key: str,
    settings: Settings,
) -> InterviewTurnAccepted:
    """Accept one first answer without reading or exposing scoring fields."""

    del client_submitted_at
    interview = await _owned_interview(session, user, interview_id, lock=True)
    turn = await _owned_turn(session, user, interview_id, turn_id, lock=True)
    key = _answer_key(user.id, interview.id, idempotency_key)
    fingerprint = _fingerprint({"turn_id": str(turn.id), "answer": answer})
    if turn.idempotency_key == key:
        if turn.answer_text != answer:
            raise AppError(
                status_code=409,
                code="idempotency_conflict",
                message="该幂等键已用于其他回答",
            )
        now = await database_now(session)
        accepted_at = turn.submitted_at or now
        progress = await _progress(session, interview, now)
        return InterviewTurnAccepted(
            turn_id=turn.id,
            state="scoring",
            accepted_at=accepted_at,
            progress=progress,
            next_action="wait",
        )
    if turn.submitted_at is not None or turn.state != "awaiting_answer":
        raise AppError(
            status_code=409,
            code="turn_already_submitted",
            message="该轮次已经提交",
        )
    now = await database_now(session)
    if interview.state != "in_progress":
        raise AppError(
            status_code=409,
            code="invalid_state_transition",
            message="面试当前不可作答",
        )
    if interview.deadline_at is None or now >= interview.deadline_at:
        await _timeout_interview(session, interview, now)
        await session.commit()
        raise AppError(
            status_code=409,
            code="interview_time_expired",
            message="面试已到达截止时间",
        )
    normalized = " ".join(answer.split())
    if not normalized:
        raise AppError(
            status_code=422,
            code="invalid_request",
            message="回答不能为空",
        )
    turn.answer_text = normalized
    turn.submitted_at = now
    turn.idempotency_key = key
    turn.state = "scoring"
    chain = (
        await session.execute(
            select(FollowUpChain)
            .where(
                FollowUpChain.interview_id == interview.id,
                FollowUpChain.root_turn_id == turn.root_turn_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if chain is not None:
        chain.answer_count = min(chain.max_answers, chain.answer_count + 1)
        chain.state = "scoring"
    await enqueue_job(
        session,
        owner_user_id=user.id,
        job_type="score_interview_turn",
        resource_type="interview_turn",
        resource_id=turn.id,
        idempotency_key=f"interview-score:{turn.id}:{key}",
        request_fingerprint=fingerprint,
        max_attempts=settings.worker_max_attempts,
    )
    view = InterviewTurnAccepted(
        turn_id=turn.id,
        state="scoring",
        accepted_at=now,
        progress=await _progress(session, interview, now),
        next_action="wait",
    )
    await session.commit()
    return view


async def _timeout_interview(
    session: AsyncSession,
    interview: Interview,
    now: datetime,
) -> None:
    if interview.state != "in_progress":
        return
    interview.state = "timed_out"
    interview.ended_at = now
    interview.end_reason = "deadline_reached"
    turns = list(
        (
            await session.execute(
                select(InterviewTurn)
                .where(InterviewTurn.interview_id == interview.id)
                .with_for_update()
            )
        ).scalars()
    )
    for turn in turns:
        if turn.state in {"pending", "awaiting_answer"}:
            turn.state = "unanswered"
            turn.end_reason = "deadline_reached"
    chains = list(
        (
            await session.execute(
                select(FollowUpChain)
                .where(FollowUpChain.interview_id == interview.id)
                .with_for_update()
            )
        ).scalars()
    )
    for chain in chains:
        if chain.state not in {"completed"}:
            chain.state = "completed"
            chain.termination_reason = "deadline_reached"


async def _branch_action(
    session: AsyncSession,
    user: User,
    interview_id: uuid.UUID,
    turn_id: uuid.UUID,
    *,
    operation: str,
    reason: str,
    idempotency_key: str,
    settings: Settings,
) -> InterviewBranchAction:
    interview = await _owned_interview(session, user, interview_id, lock=True)
    turn = await _owned_turn(session, user, interview_id, turn_id, lock=True)
    key = _operation_key(user.id, idempotency_key)
    fingerprint = _fingerprint({"turn_id": str(turn.id), "operation": operation})
    replay = await _operation_replay(
        session,
        owner_user_id=user.id,
        interview_id=interview.id,
        operation=operation,
        key=key,
        fingerprint=fingerprint,
    )
    if replay is not None:
        return InterviewBranchAction.model_validate(replay)
    now = await database_now(session)
    if interview.state != "in_progress":
        raise AppError(
            status_code=409,
            code="invalid_state_transition",
            message="面试当前不可操作",
        )
    if interview.deadline_at is None or now >= interview.deadline_at:
        await _timeout_interview(session, interview, now)
        await session.commit()
        raise AppError(
            status_code=409,
            code="interview_time_expired",
            message="面试已到达截止时间",
        )
    if turn.turn_type != "follow_up" or turn.depth < 1:
        raise AppError(
            status_code=409,
            code="invalid_branch_operation",
            message="只能对当前追问执行该操作",
        )
    if turn.state != "awaiting_answer":
        raise AppError(
            status_code=409,
            code="turn_not_awaiting_answer",
            message="当前追问不在等待回答状态",
        )
    chain = (
        await session.execute(
            select(FollowUpChain)
            .where(
                FollowUpChain.interview_id == interview.id,
                FollowUpChain.root_turn_id == turn.root_turn_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if chain is None or chain.current_turn_id != turn.id:
        raise AppError(
            status_code=409,
            code="invalid_branch_operation",
            message="只能操作当前追问",
        )
    turn.state = "skipped" if operation == "skip" else "branch_completed"
    turn.end_reason = reason
    chain.state = "completed"
    chain.termination_reason = reason
    await enqueue_job(
        session,
        owner_user_id=user.id,
        job_type="advance_interview",
        resource_type="interview",
        resource_id=interview.id,
        idempotency_key=f"interview-advance:{interview.id}:{turn.id}:{key}",
        request_fingerprint=fingerprint,
        max_attempts=settings.worker_max_attempts,
    )
    view = InterviewBranchAction(
        interview_id=interview.id,
        turn_id=turn.id,
        state=cast(Any, interview.state),
        progress=await _progress(session, interview, now),
        next_action="wait",
    )
    _store_operation(
        session,
        owner_user_id=user.id,
        interview_id=interview.id,
        operation=operation,
        key=key,
        fingerprint=fingerprint,
        response=view.model_dump(mode="json"),
    )
    await session.commit()
    return view


async def skip_turn(
    session: AsyncSession,
    user: User,
    interview_id: uuid.UUID,
    turn_id: uuid.UUID,
    *,
    idempotency_key: str,
    settings: Settings,
) -> InterviewBranchAction:
    return await _branch_action(
        session,
        user,
        interview_id,
        turn_id,
        operation="skip",
        reason="user_skipped",
        idempotency_key=idempotency_key,
        settings=settings,
    )


async def end_branch(
    session: AsyncSession,
    user: User,
    interview_id: uuid.UUID,
    turn_id: uuid.UUID,
    *,
    idempotency_key: str,
    settings: Settings,
) -> InterviewBranchAction:
    return await _branch_action(
        session,
        user,
        interview_id,
        turn_id,
        operation="end_branch",
        reason="user_ended_branch",
        idempotency_key=idempotency_key,
        settings=settings,
    )


async def _report_turn(turn: InterviewTurn) -> InterviewReportTurn:
    breakdown = turn.score_breakdown or {}
    reasons = breakdown.get("loss_reasons", [])
    return InterviewReportTurn(
        id=turn.id,
        parent_turn_id=turn.parent_turn_id,
        type=cast(Any, turn.turn_type),
        depth=turn.depth,
        question_text=turn.question_text,
        topic_key=turn.topic_key,
        difficulty=cast(Any, turn.difficulty),
        result=cast(Any, turn.state),
        score_total=float(turn.score_total) if turn.score_total is not None else None,
        score_band=cast(Any, turn.score_band),
        score_breakdown=turn.score_breakdown,
        loss_reasons=[str(value) for value in reasons] if isinstance(reasons, list) else [],
        reference_answer=turn.reference_answer
        if turn.state in {"passed", "failed", "branch_completed"}
        else None,
        submitted_at=turn.submitted_at,
    )


async def get_interview_report(
    session: AsyncSession,
    user: User,
    interview_id: uuid.UUID,
) -> InterviewReportView:
    interview = await _owned_interview(session, user, interview_id)
    now = await database_now(session)
    if (
        interview.state == "in_progress"
        and interview.deadline_at is not None
        and now >= interview.deadline_at
    ):
        await _timeout_interview(session, interview, now)
        await session.commit()
    turns = list(
        (
            await session.execute(
                select(InterviewTurn)
                .where(InterviewTurn.interview_id == interview.id)
                .order_by(InterviewTurn.sequence)
            )
        ).scalars()
    )
    if interview.state not in {"completed", "timed_out", "cancelled", "failed"}:
        raise AppError(
            status_code=409,
            code="report_not_ready",
            message="面试尚未结束",
        )
    if any(turn.state == "scoring" for turn in turns):
        raise AppError(
            status_code=409,
            code="report_not_ready",
            message="评分尚未完成",
        )
    report = (
        await session.execute(
            select(InterviewReport).where(
                InterviewReport.interview_id == interview.id,
                InterviewReport.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    summary = (report.summary_json if report is not None else {}) or {}
    questions = list(
        (
            await session.execute(
                select(WrongQuestion).where(
                    WrongQuestion.interview_id == interview.id,
                    WrongQuestion.deleted_at.is_(None),
                    WrongQuestion.expires_at > now,
                )
            )
        ).scalars()
    )
    wrong_questions = [
        WrongQuestionSummary(
            id=item.id,
            turn_id=item.turn_id,
            parent_turn_id=item.parent_turn_id,
            question_text=item.question_text,
            topic_key=item.topic_key,
            difficulty=cast(Any, item.difficulty),
            score_breakdown=item.score_breakdown,
            loss_reasons=[
                str(value) for value in item.loss_reasons.get("items", []) if isinstance(value, str)
            ],
            created_at=item.created_at,
        )
        for item in questions
    ]
    weak_rows = list(
        (
            await session.execute(
                select(WeakPoint).where(
                    WeakPoint.owner_user_id == user.id,
                    WeakPoint.deleted_at.is_(None),
                )
            )
        ).scalars()
    )
    weak_points: list[WeakPointSummary] = []
    for weak in weak_rows:
        evidence_rows = list(
            (
                await session.execute(
                    select(WeakPointEvidence).where(
                        WeakPointEvidence.weak_point_id == weak.id,
                        WeakPointEvidence.turn_id.in_({item.turn_id for item in questions}),
                    )
                )
            ).scalars()
        )
        if not evidence_rows:
            continue
        weak_points.append(
            WeakPointSummary(
                id=weak.id,
                topic_key=weak.topic_key,
                title=weak.title,
                severity=float(weak.severity),
                failure_count=weak.failure_count,
                last_failure_at=weak.last_failure_at,
                review_advice=weak.review_advice,
                state=weak.state,
                evidence=[
                    {
                        "wrong_question_id": row.wrong_question_id,
                        "turn_id": row.turn_id,
                        "loss_reason_hash": row.loss_reason_hash,
                    }
                    for row in evidence_rows
                ],
            )
        )
    scoring_status = (
        "incomplete_scoring"
        if any(turn.state == "scoring_failed" for turn in turns)
        else "complete"
    )
    return InterviewReportView(
        interview_id=interview.id,
        state=cast(Any, interview.state),
        direction=cast(Any, interview.direction),
        scoring_status=cast(Any, scoring_status),
        server_time=now,
        summary=summary,
        turns=[await _report_turn(turn) for turn in turns],
        wrong_questions=wrong_questions,
        weak_points=weak_points,
    )


def _cursor_condition(
    created_column: Any,
    id_column: Any,
    cursor: tuple[datetime, uuid.UUID] | None,
) -> Any:
    if cursor is None:
        return True
    return or_(
        created_column < cursor[0],
        and_(created_column == cursor[0], id_column < cursor[1]),
    )


def decode_review_cursor(value: str | None) -> tuple[datetime, uuid.UUID] | None:
    if value is None or not value.strip():
        return None
    try:
        raw = value.strip()
        timestamp, item_id = raw.split("|", 1)
        parsed = datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed.astimezone(UTC), uuid.UUID(item_id)
    except (TypeError, ValueError) as exc:
        raise AppError(
            status_code=400,
            code="invalid_request",
            message="分页游标不合法",
        ) from exc


def _review_cursor(item: Any) -> str:
    return f"{item.created_at.astimezone(UTC).isoformat()}|{item.id}"


async def list_wrong_questions(
    session: AsyncSession,
    user: User,
    *,
    state: str | None,
    topic: str | None,
    difficulty: str | None,
    limit: int,
    cursor: str | None,
) -> WrongQuestionPage:
    now = await database_now(session)
    parsed_cursor = decode_review_cursor(cursor)
    statement = select(WrongQuestion).where(
        WrongQuestion.owner_user_id == user.id,
        WrongQuestion.deleted_at.is_(None),
        WrongQuestion.expires_at > now,
        _cursor_condition(WrongQuestion.created_at, WrongQuestion.id, parsed_cursor),
    )
    if state:
        statement = statement.where(WrongQuestion.state == state)
    if topic:
        statement = statement.where(WrongQuestion.topic_key == topic)
    if difficulty:
        statement = statement.where(WrongQuestion.difficulty == difficulty)
    rows = list(
        (
            await session.execute(
                statement.order_by(WrongQuestion.created_at.desc(), WrongQuestion.id.desc()).limit(
                    limit + 1
                )
            )
        ).scalars()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return WrongQuestionPage(
        items=[
            WrongQuestionDetail(
                id=item.id,
                interview_id=item.interview_id,
                turn_id=item.turn_id,
                parent_turn_id=item.parent_turn_id,
                question_text=item.question_text,
                topic_key=item.topic_key,
                difficulty=cast(Any, item.difficulty),
                score_breakdown=item.score_breakdown,
                loss_reasons=[
                    str(value)
                    for value in item.loss_reasons.get("items", [])
                    if isinstance(value, str)
                ],
                created_at=item.created_at,
                answer_text=item.answer_text,
                reference_answer=item.reference_answer,
                state=item.state,
                expires_at=item.expires_at,
            )
            for item in page
        ],
        next_cursor=_review_cursor(page[-1]) if has_more and page else None,
    )


async def get_wrong_question(
    session: AsyncSession,
    user: User,
    question_id: uuid.UUID,
) -> WrongQuestionDetail:
    now = await database_now(session)
    item = (
        await session.execute(
            select(WrongQuestion).where(
                WrongQuestion.id == question_id,
                WrongQuestion.owner_user_id == user.id,
                WrongQuestion.deleted_at.is_(None),
                WrongQuestion.expires_at > now,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise AppError(
            status_code=404,
            code="resource_not_found",
            message="错题不存在",
        )
    interview = await _owned_interview(session, user, item.interview_id)
    if interview.state not in {"completed", "timed_out", "cancelled", "failed"}:
        raise AppError(
            status_code=409,
            code="feedback_locked",
            message="面试结束后才能查看完整反馈",
        )
    return WrongQuestionDetail(
        id=item.id,
        interview_id=item.interview_id,
        turn_id=item.turn_id,
        parent_turn_id=item.parent_turn_id,
        question_text=item.question_text,
        topic_key=item.topic_key,
        difficulty=cast(Any, item.difficulty),
        score_breakdown=item.score_breakdown,
        loss_reasons=[
            str(value) for value in item.loss_reasons.get("items", []) if isinstance(value, str)
        ],
        created_at=item.created_at,
        answer_text=item.answer_text,
        reference_answer=item.reference_answer,
        state=item.state,
        expires_at=item.expires_at,
    )


async def list_weak_points(
    session: AsyncSession,
    user: User,
    *,
    state: str | None,
    limit: int,
    cursor: str | None,
) -> WeakPointPage:
    parsed_cursor = decode_review_cursor(cursor)
    statement = select(WeakPoint).where(
        WeakPoint.owner_user_id == user.id,
        WeakPoint.deleted_at.is_(None),
        _cursor_condition(WeakPoint.created_at, WeakPoint.id, parsed_cursor),
    )
    if state:
        statement = statement.where(WeakPoint.state == state)
    rows = list(
        (
            await session.execute(
                statement.order_by(
                    WeakPoint.severity.desc(),
                    WeakPoint.failure_count.desc(),
                    WeakPoint.last_failure_at.desc(),
                    WeakPoint.id.desc(),
                ).limit(limit + 1)
            )
        ).scalars()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    items: list[WeakPointSummary] = []
    for item in page:
        evidence = list(
            (
                await session.execute(
                    select(WeakPointEvidence).where(WeakPointEvidence.weak_point_id == item.id)
                )
            ).scalars()
        )
        items.append(
            WeakPointSummary(
                id=item.id,
                topic_key=item.topic_key,
                title=item.title,
                severity=float(item.severity),
                failure_count=item.failure_count,
                last_failure_at=item.last_failure_at,
                review_advice=item.review_advice,
                state=item.state,
                evidence=[
                    WeakPointEvidenceView(
                        wrong_question_id=row.wrong_question_id,
                        turn_id=row.turn_id,
                        loss_reason_hash=row.loss_reason_hash,
                    )
                    for row in evidence
                ],
            )
        )
    return WeakPointPage(
        items=items,
        next_cursor=_review_cursor(page[-1]) if has_more and page else None,
    )


async def get_weak_point(
    session: AsyncSession,
    user: User,
    weak_point_id: uuid.UUID,
) -> WeakPointSummary:
    item = (
        await session.execute(
            select(WeakPoint).where(
                WeakPoint.id == weak_point_id,
                WeakPoint.owner_user_id == user.id,
                WeakPoint.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise AppError(
            status_code=404,
            code="resource_not_found",
            message="薄弱点不存在",
        )
    evidence = list(
        (
            await session.execute(
                select(WeakPointEvidence).where(WeakPointEvidence.weak_point_id == item.id)
            )
        ).scalars()
    )
    return WeakPointSummary(
        id=item.id,
        topic_key=item.topic_key,
        title=item.title,
        severity=float(item.severity),
        failure_count=item.failure_count,
        last_failure_at=item.last_failure_at,
        review_advice=item.review_advice,
        state=item.state,
        evidence=[
            WeakPointEvidenceView(
                wrong_question_id=row.wrong_question_id,
                turn_id=row.turn_id,
                loss_reason_hash=row.loss_reason_hash,
            )
            for row in evidence
        ],
    )


__all__ = [
    "create_interview",
    "database_now",
    "end_branch",
    "get_interview",
    "get_interview_report",
    "get_weak_point",
    "get_wrong_question",
    "list_weak_points",
    "list_wrong_questions",
    "skip_turn",
    "start_interview",
    "submit_answer",
]
