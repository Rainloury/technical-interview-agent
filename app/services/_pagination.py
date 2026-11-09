"""service 层不透明时间戳游标的共享编解码与比较条件。"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_, true
from sqlalchemy.sql.elements import ColumnElement

from app.errors import AppError


@dataclass(frozen=True, slots=True)
class Cursor:
    """稳定的时间戳与 UUID 决胜键。"""

    timestamp: datetime
    id: uuid.UUID


def encode_cursor(cursor: Cursor, *, field: str = "created_at") -> str:
    payload = json.dumps(
        {field: cursor.timestamp.astimezone(UTC).isoformat(), "id": str(cursor.id)},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(value: str, *, field: str = "created_at") -> Cursor:
    """将格式错误或缺少时区的游标视为无效请求拒绝。"""

    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        timestamp = datetime.fromisoformat(str(payload[field]))
        if timestamp.tzinfo is None:
            raise ValueError("cursor timestamp must include a timezone")
        return Cursor(
            timestamp=timestamp.astimezone(UTC),
            id=uuid.UUID(str(payload["id"])),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            status_code=400,
            code="invalid_request",
            message="分页游标不合法",
        ) from exc


def decode_legacy_cursor(value: str) -> Cursor:
    """兼容期内解析旧版 ``timestamp|uuid`` 明文复习游标。"""

    try:
        timestamp, item_id = value.strip().split("|", 1)
        parsed = datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return Cursor(timestamp=parsed.astimezone(UTC), id=uuid.UUID(item_id))
    except (TypeError, ValueError) as exc:
        raise AppError(
            status_code=400,
            code="invalid_request",
            message="分页游标不合法",
        ) from exc


def decode_cursor_with_legacy(value: str | None) -> Cursor | None:
    """先尝试不透明游标,兼容期内回退到旧明文格式。"""

    if value is None or not value.strip():
        return None
    if "|" in value:
        return decode_legacy_cursor(value)
    return decode_cursor(value)


def cursor_condition(
    timestamp_column: Any,
    id_column: Any,
    cursor: Cursor | None,
) -> ColumnElement[bool]:
    if cursor is None:
        return true()
    return or_(
        timestamp_column < cursor.timestamp,
        and_(timestamp_column == cursor.timestamp, id_column < cursor.id),
    )


def next_cursor(
    items: list[Any],
    *,
    has_more: bool,
    timestamp_field: str = "created_at",
) -> str | None:
    if not has_more or not items:
        return None
    last = items[-1]
    return encode_cursor(
        Cursor(timestamp=getattr(last, timestamp_field), id=last.id),
        field=timestamp_field,
    )
