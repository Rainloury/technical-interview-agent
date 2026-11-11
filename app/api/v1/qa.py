"""按所有者隔离的检索问答创建、详情和可恢复 SSE 流。"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dependencies import (
    AuthDependency,
    CursorDependency,
    IdempotencyKeyDependency,
    SessionDependency,
    SessionFactoryDependency,
    SettingsDependency,
    verify_write_security,
)
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
    settings: SettingsDependency,
) -> QaAccepted:
    """接受一个白名单内的检索问题并为其回答任务入队。"""

    verify_write_security(request, auth, settings)
    return await create_qa_request(
        session,
        auth.user,
        payload,
        idempotency_key=idempotency_key,
        settings=settings,
    )


@router.get("/{request_id}", response_model=QaRequestView)
async def read_question(
    request_id: uuid.UUID,
    auth: AuthDependency,
    session: SessionDependency,
) -> QaRequestView:
    """返回所有者当前状态、最终回答和公开证据。"""

    return await get_qa_request(session, auth.user, request_id)


async def _stream_events(
    session_factory: async_sessionmaker[AsyncSession],
    request_id: uuid.UUID,
    *,
    after_seq: int,
) -> AsyncIterator[str]:
    """轮询持久事件,睡眠期间不持有数据库会话。"""

    cursor = after_seq
    idle_polls = 0
    while True:
        async with session_factory() as session:
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
    auth: AuthDependency,
    session: SessionDependency,
    session_factory: SessionFactoryDependency,
    cursor: CursorDependency,
) -> StreamingResponse:
    """发送持久问答事件,并严格在提供的游标之后恢复。"""

    await assert_stream_owner(session, auth.user, request_id)
    await session.rollback()
    return StreamingResponse(
        _stream_events(session_factory, request_id, after_seq=cursor),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
