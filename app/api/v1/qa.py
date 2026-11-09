"""按所有者隔离的检索问答创建、详情和可恢复 SSE 流。"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import (
    AuthDependency,
    IdempotencyKeyDependency,
    SessionDependency,
    verify_write_security,
)
from app.errors import AppError
from app.schemas.qa import QaAccepted, QaCreate, QaRequestView
from app.services.qa import (
    assert_stream_owner,
    create_qa_request,
    events_after,
    get_qa_request,
)

router = APIRouter(prefix="/qa", tags=["qa"])


def _format_event(event_type: str, event_id: int, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_type}\nid: {event_id}\ndata: {data}\n\n"


@router.post("", response_model=QaAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_question(
    payload: QaCreate,
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    idempotency_key: IdempotencyKeyDependency,
) -> QaAccepted:
    """接受一个白名单内的检索问题并为其回答任务入队。"""

    verify_write_security(request, auth)
    return await create_qa_request(
        session,
        auth.user,
        payload,
        idempotency_key=idempotency_key,
        settings=request.app.state.settings,
    )


@router.get("/{request_id}", response_model=QaRequestView)
async def read_question(
    request_id: uuid.UUID,
    auth: AuthDependency,
    session: SessionDependency,
) -> QaRequestView:
    """返回所有者当前状态、最终回答和公开证据。"""

    return await get_qa_request(session, auth.user, request_id)


def _parse_cursor(
    after_seq: int | None = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> int:
    """优先使用显式游标,否则解析 SSE 重连头。"""

    if after_seq is not None:
        if after_seq < 0:
            raise AppError(
                status_code=400,
                code="invalid_request",
                message="事件游标不合法",
            )
        return after_seq
    if last_event_id is None or not last_event_id.strip():
        return 0
    try:
        cursor = int(last_event_id)
    except ValueError as exc:
        raise AppError(
            status_code=400,
            code="invalid_request",
            message="事件游标不合法",
        ) from exc
    if cursor < 0:
        raise AppError(
            status_code=400,
            code="invalid_request",
            message="事件游标不合法",
        )
    return cursor


async def _stream_events(
    request: Request,
    request_id: uuid.UUID,
    *,
    after_seq: int,
) -> AsyncIterator[str]:
    """轮询持久事件,睡眠期间不持有数据库会话。"""

    cursor = after_seq
    idle_polls = 0
    while True:
        async with request.app.state.session_factory() as session:
            events, terminal = await events_after(
                session,
                request_id,
                after_seq=cursor,
            )
            rendered = [
                _format_event(event.event_type, event.seq, event.payload_json) for event in events
            ]
            if rendered:
                cursor = events[-1].seq
        if rendered:
            idle_polls = 0
            for item in rendered:
                yield item
        if terminal:
            return
        idle_polls += 1
        if idle_polls % 100 == 0:
            yield ": keep-alive\n\n"
        await asyncio.sleep(0.25)


@router.get("/{request_id}/stream")
async def stream_question(
    request_id: uuid.UUID,
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    cursor: Annotated[int, Depends(_parse_cursor)],
) -> StreamingResponse:
    """发送持久问答事件,并严格在提供的游标之后恢复。"""

    await assert_stream_owner(session, auth.user, request_id)
    await session.rollback()
    return StreamingResponse(
        _stream_events(request, request_id, after_seq=cursor),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
