"""映射到 PostgreSQL 原生类型的可移植列类型。"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator


class UUIDType(TypeDecorator[uuid.UUID]):
    """在 PostgreSQL 上原生存储的 UUID。"""

    impl = Uuid
    cache_ok = True
    python_type = uuid.UUID


class UTCDateTime(TypeDecorator[datetime]):
    """保证为 UTC 的时区感知 datetime。"""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("datetime values must be timezone-aware")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value


class JSONBType(TypeDecorator[dict[str, Any]]):
    """在 PostgreSQL 上以 JSONB 存储的 JSON 载荷。"""

    impl = JSONB
    cache_ok = True
