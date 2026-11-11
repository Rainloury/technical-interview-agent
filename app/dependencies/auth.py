"""认证、授权与写操作安全依赖。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.db.models import AuthSession, User
from app.dependencies.db import SessionDependency
from app.dependencies.resources import SettingsDependency
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


async def get_auth_context(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AuthContext:
    """为活跃会话解析并持久化最后活跃时间。"""

    raw_token = request.cookies.get(settings.session_cookie_name)
    user, auth_session = await current_auth(session, raw_token=raw_token)
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
    settings: SettingsDependency,
) -> AuthContext:
    """为活跃或已匿名化的所有者认证删除状态读取。"""

    raw_token = request.cookies.get(settings.session_cookie_name)
    user, auth_session = await current_auth_for_deletion_status(session, raw_token=raw_token)
    await session.commit()
    return AuthContext(user=user, session=auth_session)


DeletionStatusAuthDependency = Annotated[
    AuthContext,
    Depends(get_deletion_status_auth),
]


def verify_write_security(
    request: Request,
    auth: AuthContext,
    settings: Settings,
) -> None:
    """对已认证的写操作应用来源与 CSRF 校验。"""

    verify_csrf(request, settings, auth.session)
