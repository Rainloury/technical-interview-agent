"""按所有者隔离的面试、报告、错题和薄弱点端点。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import (
    AuthDependency,
    IdempotencyKeyDependency,
    SessionDependency,
    SettingsDependency,
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
    """一道首次答案;客户端时间仅用于诊断。"""

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
    settings: SettingsDependency,
) -> InterviewCreated:
    """创建一份冻结的面试配置和蓝图。"""

    verify_write_security(request, auth, settings)
    return await create_interview(
        session,
        auth.user,
        payload,
        idempotency_key=idempotency_key,
        settings=settings,
    )


@router.post("/{interview_id}/start", response_model=InterviewStartView)
async def start(
    interview_id: uuid.UUID,
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    idempotency_key: IdempotencyKeyDependency,
    settings: SettingsDependency,
) -> InterviewStartView:
    """仅启动一次并仅返回当前公开问题和中性进度。"""

    verify_write_security(request, auth, settings)
    return await start_interview(
        session,
        auth.user,
        interview_id,
        idempotency_key=idempotency_key,
        settings=settings,
    )


@router.get("/{interview_id}", response_model=InterviewView)
async def detail(
    interview_id: uuid.UUID,
    auth: AuthDependency,
    session: SessionDependency,
) -> InterviewView:
    """恢复所属面试且不暴露受保护的反馈。"""

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
    settings: SettingsDependency,
) -> InterviewTurnAccepted:
    """接受一道答案并排队独立评分。"""

    verify_write_security(request, auth, settings)
    return await submit_answer(
        session,
        auth.user,
        interview_id,
        turn_id,
        answer=payload.answer,
        client_submitted_at=payload.client_submitted_at,
        idempotency_key=idempotency_key,
        settings=settings,
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
    settings: SettingsDependency,
) -> InterviewBranchAction:
    """跳过当前追问而不结束面试。"""

    verify_write_security(request, auth, settings)
    return await skip_turn(
        session,
        auth.user,
        interview_id,
        turn_id,
        idempotency_key=idempotency_key,
        settings=settings,
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
    settings: SettingsDependency,
) -> InterviewBranchAction:
    """仅结束当前追问链并记录其独立原因。"""

    verify_write_security(request, auth, settings)
    return await end_branch(
        session,
        auth.user,
        interview_id,
        turn_id,
        idempotency_key=idempotency_key,
        settings=settings,
    )


@router.get("/{interview_id}/report", response_model=InterviewReportView)
async def report(
    interview_id: uuid.UUID,
    auth: AuthDependency,
    session: SessionDependency,
) -> InterviewReportView:
    """仅在面试和评分落定后解锁受保护的反馈。"""

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
    """仅列出调用方未过期的错题。"""

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
