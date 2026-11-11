"""SSE 事件游标依赖。"""

from typing import Annotated

from fastapi import Depends, Header

from app.errors import AppError


def parse_cursor(
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


CursorDependency = Annotated[int, Depends(parse_cursor)]
