"""Portable column types that map to PostgreSQL-native types."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator


class UUIDType(TypeDecorator[uuid.UUID]):
    """UUID stored natively on PostgreSQL."""

    impl = Uuid
    cache_ok = True
    python_type = uuid.UUID


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware datetime guaranteed to be UTC."""

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
    """JSON payload stored as JSONB on PostgreSQL."""

    impl = JSONB
    cache_ok = True
