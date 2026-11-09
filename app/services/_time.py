"""service 层统一使用 PostgreSQL 语句时间。"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def database_now(session: AsyncSession) -> datetime:
    value = (await session.execute(select(func.statement_timestamp()))).scalar_one()
    return cast(datetime, value)
