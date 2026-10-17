"""Cursor-paginated owner history."""

from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement, SQLColumnExpression

from app.db.models import Interview, QaRequest, ResumeFile, ResumeTask, User, WrongQuestion
from app.errors import AppError
from app.schemas.history import HistoryItem, HistoryPage, HistoryType

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class HistoryCursor:
    """Stable timestamp and UUID tie-breaker."""

    updated_at: datetime
    id: uuid.UUID


def encode_cursor(cursor: HistoryCursor) -> str:
    """Encode a URL-safe, opaque pagination cursor."""

    payload = json.dumps(
        {"updated_at": cursor.updated_at.astimezone(UTC).isoformat(), "id": str(cursor.id)},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(value: str) -> HistoryCursor:
    """Reject malformed or timezone-free cursors as invalid requests."""

    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        updated_at = datetime.fromisoformat(str(payload["updated_at"]))
        if updated_at.tzinfo is None:
            raise ValueError("cursor timestamp must include a timezone")
        return HistoryCursor(
            updated_at=updated_at.astimezone(UTC),
            id=uuid.UUID(str(payload["id"])),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            status_code=400,
            code="invalid_request",
            message="分页游标不合法",
        ) from exc


def _short_title(value: str, fallback: str) -> str:
    normalized = _WHITESPACE.sub(" ", value).strip()
    if not normalized:
        return fallback
    return normalized if len(normalized) <= 100 else f"{normalized[:97]}..."


def _page_condition(
    updated: SQLColumnExpression[datetime | None],
    primary_id: SQLColumnExpression[uuid.UUID],
    cursor: HistoryCursor | None,
) -> ColumnElement[bool]:
    if cursor is None:
        return true()
    return or_(
        updated < cursor.updated_at,
        and_(updated == cursor.updated_at, primary_id < cursor.id),
    )


async def list_history(
    session: AsyncSession,
    user: User,
    *,
    history_type: HistoryType,
    limit: int,
    cursor: HistoryCursor | None,
) -> HistoryPage:
    """Return a stable descending page for one history collection."""

    now = datetime.now(UTC)
    rows: list[tuple[uuid.UUID, HistoryType, str, str, datetime]]

    if history_type == "resume":
        updated = func.coalesce(
            ResumeTask.completed_at,
            ResumeTask.started_at,
            ResumeTask.created_at,
        )
        resume_result = await session.execute(
            select(ResumeTask, ResumeFile.original_filename, updated.label("updated_at"))
            .outerjoin(
                ResumeFile,
                (ResumeFile.resume_task_id == ResumeTask.id) & ResumeFile.deleted_at.is_(None),
            )
            .where(
                ResumeTask.owner_user_id == user.id,
                ResumeTask.deleted_at.is_(None),
                ResumeTask.expires_at > now,
                _page_condition(updated, ResumeTask.id, cursor),
            )
            .order_by(updated.desc(), ResumeTask.id.desc())
            .limit(limit + 1)
        )
        rows = [
            (
                task.id,
                "resume",
                _short_title(filename or "", "简历任务"),
                task.state,
                row_updated,
            )
            for task, filename, row_updated in resume_result.all()
        ]
    elif history_type == "qa":
        updated = func.coalesce(QaRequest.completed_at, QaRequest.created_at)
        qa_result = await session.execute(
            select(QaRequest, updated.label("updated_at"))
            .where(
                QaRequest.owner_user_id == user.id,
                QaRequest.deleted_at.is_(None),
                QaRequest.expires_at > now,
                _page_condition(updated, QaRequest.id, cursor),
            )
            .order_by(updated.desc(), QaRequest.id.desc())
            .limit(limit + 1)
        )
        rows = [
            (
                request.id,
                "qa",
                _short_title(request.question_text, "技术问答"),
                request.state,
                row_updated,
            )
            for request, row_updated in qa_result.all()
        ]
    elif history_type == "interview":
        updated = func.coalesce(Interview.ended_at, Interview.started_at, Interview.created_at)
        interview_result = await session.execute(
            select(Interview, updated.label("updated_at"))
            .where(
                Interview.owner_user_id == user.id,
                Interview.deleted_at.is_(None),
                Interview.expires_at > now,
                _page_condition(updated, Interview.id, cursor),
            )
            .order_by(updated.desc(), Interview.id.desc())
            .limit(limit + 1)
        )
        rows = [
            (
                interview.id,
                "interview",
                {
                    "backend": "后端方向模拟面试",
                    "frontend": "前端方向模拟面试",
                    "fullstack": "全栈方向模拟面试",
                }.get(interview.direction, "模拟面试"),
                interview.state,
                row_updated,
            )
            for interview, row_updated in interview_result.all()
        ]
    else:
        wrong_question_result = await session.execute(
            select(WrongQuestion, WrongQuestion.updated_at.label("updated_at"))
            .where(
                WrongQuestion.owner_user_id == user.id,
                WrongQuestion.deleted_at.is_(None),
                WrongQuestion.expires_at > now,
                _page_condition(WrongQuestion.updated_at, WrongQuestion.id, cursor),
            )
            .order_by(WrongQuestion.updated_at.desc(), WrongQuestion.id.desc())
            .limit(limit + 1)
        )
        rows = [
            (
                question.id,
                "wrong_question",
                _short_title(question.question_text, "错题"),
                question.state,
                row_updated,
            )
            for question, row_updated in wrong_question_result.all()
        ]

    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = None
    if has_more and page_rows:
        last_id, _, _, _, last_updated = page_rows[-1]
        next_cursor = encode_cursor(HistoryCursor(updated_at=last_updated, id=last_id))
    return HistoryPage(
        items=[
            HistoryItem(
                id=item_id,
                type=item_type,
                title=title,
                state=state,
                updated_at=updated_at,
            )
            for item_id, item_type, title, state, updated_at in page_rows
        ],
        next_cursor=next_cursor,
    )
