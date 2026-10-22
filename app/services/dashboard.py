"""Owner-scoped workspace summaries."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Interview, QaRequest, ResumeFile, ResumeTask, User
from app.schemas.auth import UserSummary
from app.schemas.dashboard import DashboardResponse, RecentInterview, RecentTask

_WHITESPACE = re.compile(r"\s+")


def _short_title(value: str, fallback: str) -> str:
    normalized = _WHITESPACE.sub(" ", value).strip()
    if not normalized:
        return fallback
    return normalized if len(normalized) <= 80 else f"{normalized[:77]}..."


async def get_dashboard(session: AsyncSession, user: User) -> DashboardResponse:
    """Return recent owned work without exposing content bodies."""

    now = datetime.now(UTC)
    resume_updated = func.coalesce(
        ResumeTask.completed_at,
        ResumeTask.started_at,
        ResumeTask.created_at,
    )
    resume_rows = (
        await session.execute(
            select(ResumeTask, ResumeFile.original_filename, resume_updated.label("updated_at"))
            .outerjoin(
                ResumeFile,
                (ResumeFile.resume_task_id == ResumeTask.id) & ResumeFile.deleted_at.is_(None),
            )
            .where(
                ResumeTask.owner_user_id == user.id,
                ResumeTask.deleted_at.is_(None),
                ResumeTask.expires_at > now,
            )
            .order_by(resume_updated.desc(), ResumeTask.id.desc())
            .limit(5)
        )
    ).all()
    qa_updated = func.coalesce(QaRequest.completed_at, QaRequest.created_at)
    qa_rows = (
        await session.execute(
            select(QaRequest, qa_updated.label("updated_at"))
            .where(
                QaRequest.owner_user_id == user.id,
                QaRequest.deleted_at.is_(None),
                QaRequest.expires_at > now,
            )
            .order_by(qa_updated.desc(), QaRequest.id.desc())
            .limit(5)
        )
    ).all()

    tasks = [
        RecentTask(
            id=task.id,
            type="resume",
            title=_short_title(filename or "", "简历任务"),
            state=task.state,
            updated_at=updated_at,
        )
        for task, filename, updated_at in resume_rows
    ]
    tasks.extend(
        RecentTask(
            id=request.id,
            type="qa",
            title=_short_title(request.question_text, "技术问答"),
            state=request.state,
            updated_at=updated_at,
        )
        for request, updated_at in qa_rows
    )
    tasks.sort(key=lambda item: (item.updated_at, item.id), reverse=True)

    interview_updated = func.coalesce(
        Interview.ended_at,
        Interview.started_at,
        Interview.created_at,
    )
    interview_rows = (
        await session.execute(
            select(Interview, interview_updated.label("updated_at"))
            .where(
                Interview.owner_user_id == user.id,
                Interview.deleted_at.is_(None),
                Interview.expires_at > now,
            )
            .order_by(interview_updated.desc(), Interview.id.desc())
            .limit(5)
        )
    ).all()

    return DashboardResponse(
        user=UserSummary(id=user.id, display_name=user.display_name, role=user.role),
        recent_tasks=tasks[:5],
        recent_interviews=[
            RecentInterview(
                id=interview.id,
                direction=interview.direction,
                state=interview.state,
                updated_at=updated_at,
            )
            for interview, updated_at in interview_rows
        ],
        server_time=now,
    )
