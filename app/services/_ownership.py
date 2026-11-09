"""按所有者隔离资源的共享查询与错误映射。"""

from __future__ import annotations

import uuid
from typing import Any, TypeVar, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.errors import AppError

ModelT = TypeVar("ModelT")


async def get_owned(
    session: AsyncSession,
    model: Any,
    user: User | None,
    resource_id: uuid.UUID,
    *,
    message: str,
    lock: bool = False,
    include_deleted: bool = False,
    owner_column: str = "owner_user_id",
    with_owner_scope: bool = True,
) -> ModelT:
    """返回当前用户拥有的未删除资源,否则抛出统一的 404。"""

    columns = cast(Any, model)
    statement = select(columns).where(columns.id == resource_id)
    if with_owner_scope and user is not None:
        statement = statement.where(getattr(columns, owner_column) == user.id)
    if not include_deleted and hasattr(columns, "deleted_at"):
        statement = statement.where(columns.deleted_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    resource = (await session.execute(statement)).scalar_one_or_none()
    if resource is None:
        raise AppError(
            status_code=404,
            code="resource_not_found",
            message=message,
        )
    return cast(ModelT, resource)
