"""Owner-scoped interview, report, wrong-question, and weak-point endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import (
    AuthDependency,
    IdempotencyKeyDependency,
    SessionDependency,
    verify_write_security,
)
from app.schemas.interview import (
    InterviewBranchAction,
    InterviewCreate,
    InterviewCreated,
    InterviewReportView,
    InterviewStartView,
    InterviewTurnAccepted,
    InterviewView,
    WeakPointPage,
    WeakPointSummary,
    WrongQuestionDetail,
    WrongQuestionPage,
)
from app.services.interviews import (
    create_interview,
    end_branch,
    get_interview,
    get_interview_report,
    get_weak_point,
    get_wrong_question,
    list_weak_points,
    list_wrong_questions,
    skip_turn,
    start_interview,
    submit_answer,
)

router = APIRouter(prefix="/interviews", tags=["interviews"])
reviews_router = APIRouter(tags=["reviews"])


class InterviewAnswer(BaseModel):
    """One first answer; client time is diagnostic only."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=20_000)
    client_submitted_at: datetime | None = None


@router.post("", response_model=InterviewCreated, status_code=status.HTTP_201_CREATED)
async def create(
    payload: InterviewCreate,
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    idempotency_key: IdempotencyKeyDependency,
) -> InterviewCreated:
    """Create one frozen interview configuration and blueprint."""

    verify_write_security(request, auth)
    return await create_interview(
        session,
        auth.user,
        payload,
        idempotency_key=idempotency_key,
        settings=request.app.state.settings,
    )


@router.post("/{interview_id}/start", response_model=InterviewStartView)
async def start(
    interview_id: uuid.UUID,
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    idempotency_key: IdempotencyKeyDependency,
) -> InterviewStartView:
    """Start once and return only the current public question and neutral progress."""

    verify_write_security(request, auth)
    return await start_interview(
        session,
        auth.user,
        interview_id,
        idempotency_key=idempotency_key,
        settings=request.app.state.settings,
    )


@router.get("/{interview_id}", response_model=InterviewView)
async def detail(
    interview_id: uuid.UUID,
    auth: AuthDependency,
    session: SessionDependency,
) -> InterviewView:
    """Resume an owned interview without exposing protected feedback."""

    return await get_interview(session, auth.user, interview_id)


@router.post(
    "/{interview_id}/turns/{turn_id}/answer",
    response_model=InterviewTurnAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def answer(
    interview_id: uuid.UUID,
    turn_id: uuid.UUID,
    payload: InterviewAnswer,
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    idempotency_key: IdempotencyKeyDependency,
) -> InterviewTurnAccepted:
    """Accept one answer and enqueue independent scoring."""

    verify_write_security(request, auth)
    return await submit_answer(
        session,
        auth.user,
        interview_id,
        turn_id,
        answer=payload.answer,
        client_submitted_at=payload.client_submitted_at,
        idempotency_key=idempotency_key,
        settings=request.app.state.settings,
    )


@router.post(
    "/{interview_id}/turns/{turn_id}/skip",
    response_model=InterviewBranchAction,
)
async def skip(
    interview_id: uuid.UUID,
    turn_id: uuid.UUID,
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    idempotency_key: IdempotencyKeyDependency,
) -> InterviewBranchAction:
    """Skip the current follow-up without ending the interview."""

    verify_write_security(request, auth)
    return await skip_turn(
        session,
        auth.user,
        interview_id,
        turn_id,
        idempotency_key=idempotency_key,
        settings=request.app.state.settings,
    )


@router.post(
    "/{interview_id}/turns/{turn_id}/end-branch",
    response_model=InterviewBranchAction,
)
async def end_current_branch(
    interview_id: uuid.UUID,
    turn_id: uuid.UUID,
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    idempotency_key: IdempotencyKeyDependency,
) -> InterviewBranchAction:
    """End only the current follow-up chain and record its distinct reason."""

    verify_write_security(request, auth)
    return await end_branch(
        session,
        auth.user,
        interview_id,
        turn_id,
        idempotency_key=idempotency_key,
        settings=request.app.state.settings,
    )


@router.get("/{interview_id}/report", response_model=InterviewReportView)
async def report(
    interview_id: uuid.UUID,
    auth: AuthDependency,
    session: SessionDependency,
) -> InterviewReportView:
    """Unlock protected feedback only after the interview and scoring settle."""

    return await get_interview_report(session, auth.user, interview_id)


@reviews_router.get("/wrong-questions", response_model=WrongQuestionPage)
async def wrong_questions(
    auth: AuthDependency,
    session: SessionDependency,
    state: str | None = None,
    topic: str | None = None,
    difficulty: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> WrongQuestionPage:
    """List only the caller's unexpired wrong questions."""

    return await list_wrong_questions(
        session,
        auth.user,
        state=state,
        topic=topic,
        difficulty=difficulty,
        limit=limit,
        cursor=cursor,
    )


@reviews_router.get("/wrong-questions/{question_id}", response_model=WrongQuestionDetail)
async def wrong_question(
    question_id: uuid.UUID,
    auth: AuthDependency,
    session: SessionDependency,
) -> WrongQuestionDetail:
    return await get_wrong_question(session, auth.user, question_id)


@reviews_router.get("/weak-points", response_model=WeakPointPage)
async def weak_points(
    auth: AuthDependency,
    session: SessionDependency,
    state: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> WeakPointPage:
    return await list_weak_points(
        session,
        auth.user,
        state=state,
        limit=limit,
        cursor=cursor,
    )


@reviews_router.get("/weak-points/{weak_point_id}", response_model=WeakPointSummary)
async def weak_point(
    weak_point_id: uuid.UUID,
    auth: AuthDependency,
    session: SessionDependency,
) -> WeakPointSummary:
    return await get_weak_point(session, auth.user, weak_point_id)
