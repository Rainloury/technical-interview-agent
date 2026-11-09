"""共享 API 认证与数据库依赖。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuthSession, User
from app.db.session import get_session
from app.errors import AppError
from app.services.auth import (
    current_auth,
    current_auth_for_deletion_status,
    verify_csrf,
)


@dataclass(frozen=True, slots=True)
class AuthContext:
    """已认证用户及用于授权该用户的服务端会话。"""

    user: User
    session: AuthSession


SessionDependency = Annotated[AsyncSession, Depends(get_session)]


async def get_auth_context(request: Request, session: SessionDependency) -> AuthContext:
    """为活跃会话解析并持久化最后活跃时间。"""

    user, auth_session = await current_auth(session, request)
    await session.commit()
    return AuthContext(user=user, session=auth_session)


AuthDependency = Annotated[AuthContext, Depends(get_auth_context)]


def require_admin(auth: AuthContext) -> None:
    """写操作需要基于数据库的管理员角色。"""

    if auth.user.role != "admin":
        raise AppError(
            status_code=403,
            code="admin_required",
            message="只有管理员可以管理共享资料",
        )


async def get_deletion_status_auth(
    request: Request,
    session: SessionDependency,
) -> AuthContext:
    """为活跃或已匿名化的所有者认证删除状态读取。"""

    user, auth_session = await current_auth_for_deletion_status(session, request)
    await session.commit()
    return AuthContext(user=user, session=auth_session)


DeletionStatusAuthDependency = Annotated[AuthContext, Depends(get_deletion_status_auth)]


def require_idempotency_key(
    value: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    """变更操作需要一个有界的不透明幂等键。"""

    if value is None or not value.strip():
        raise AppError(
            status_code=400,
            code="idempotency_key_required",
            message="缺少 Idempotency-Key",
        )
    normalized = value.strip()
    if len(normalized) > 200:
        raise AppError(
            status_code=400,
            code="invalid_request",
            message="Idempotency-Key 过长",
        )
    return normalized


IdempotencyKeyDependency = Annotated[str, Depends(require_idempotency_key)]


def verify_write_security(request: Request, auth: AuthContext) -> None:
    """对已认证的写操作应用来源与 CSRF 校验。"""

    verify_csrf(request, request.app.state.settings, auth.session)
