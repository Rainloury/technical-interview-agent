"""Shared API authentication and database dependencies."""

from __future__ import annotations

import hashlib
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
    """Authenticated user and the server-side session used to authorize it."""

    user: User
    session: AuthSession


SessionDependency = Annotated[AsyncSession, Depends(get_session)]


async def get_auth_context(request: Request, session: SessionDependency) -> AuthContext:
    """Resolve and persist last-seen activity for a live session."""

    user, auth_session = await current_auth(session, request)
    await session.commit()
    return AuthContext(user=user, session=auth_session)


AuthDependency = Annotated[AuthContext, Depends(get_auth_context)]


def require_admin(auth: AuthContext) -> None:
    """Require the database-backed administrator role for a write operation."""

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
    """Authenticate deletion-status reads for active or anonymized owners."""

    user, auth_session = await current_auth_for_deletion_status(session, request)
    await session.commit()
    return AuthContext(user=user, session=auth_session)


DeletionStatusAuthDependency = Annotated[AuthContext, Depends(get_deletion_status_auth)]


def require_idempotency_key(
    value: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    """Require one bounded opaque idempotency key for mutating operations."""

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
    """Apply origin and CSRF verification to an authenticated write."""

    verify_csrf(request, request.app.state.settings, auth.session)


def hash_idempotency_key(value: str) -> str:
    """Store only a hash of caller-provided idempotency material."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()
