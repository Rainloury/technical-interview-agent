"""数据库会话依赖。"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.state import app_state


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """生成请求作用域会话。"""

    factory = app_state(request).session_factory
    async with factory() as session:
        yield session


SessionDependency = Annotated[AsyncSession, Depends(get_session)]
