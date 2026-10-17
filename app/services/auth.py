"""Authentication and server-side session lifecycle."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request
from redis.exceptions import RedisError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import AuditEvent, AuthSession, PasswordResetToken, User
from app.errors import AppError
from app.logging import get_logger
from app.security import (
    check_write_origin,
    dummy_password_hash,
    hash_password,
    normalize_email,
    opaque_token,
    token_hash,
    tokens_equal,
    validate_password,
    verify_password,
)

logger = get_logger("app.auth")


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """A raw session token and public session metadata."""

    raw_token: str
    csrf_token: str
    expires_at: datetime
    user: User
    session_id: uuid.UUID


async def audit(
    session: AsyncSession,
    *,
    action: str,
    resource_type: str = "user",
    resource_id_hash: str,
    result: str,
    request_id: str,
) -> None:
    """Append a minimal, non-reversible audit record."""

    session.add(
        AuditEvent(
            action=action,
            resource_type=resource_type,
            resource_id_hash=resource_id_hash,
            result=result,
            request_id=request_id[:120] or uuid.uuid4().hex,
        )
    )


async def _limited(request: Request, key: str, limit: int) -> None:
    """Apply a Redis-backed fixed-window limiter."""

    bucket = f"auth:rate:{key}"
    redis = request.app.state.redis
    try:
        count = await redis.incr(bucket)
        if count == 1:
            await redis.expire(bucket, 60)
        if count > limit:
            raise AppError(
                status_code=429,
                code="rate_limited",
                message="请求过于频繁，请稍后重试",
                retryable=True,
            )
    except AppError:
        raise
    except RedisError as exc:
        logger.warning("auth rate limiter unavailable", error_code=type(exc).__name__)
        raise AppError(
            status_code=503,
            code="service_unavailable",
            message="认证服务暂时不可用",
            retryable=True,
        ) from exc


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    request: Request,
    settings: Settings,
) -> None:
    """Create a user or return the same neutral outcome."""

    validate_password(password)
    check_write_origin(request, settings)
    normalized = normalize_email(email)
    request_id = getattr(request.state, "request_id", "unknown")
    await _limited(
        request,
        f"register:ip:{request.client.host if request.client else 'unknown'}",
        settings.auth_rate_limit_per_minute,
    )
    account_key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    await _limited(
        request,
        f"register:account:{account_key}",
        settings.auth_rate_limit_per_minute,
    )
    password_hash = hash_password(password)
    try:
        async with session.begin_nested():
            user = User(email_normalized=normalized, password_hash=password_hash)
            session.add(user)
            await session.flush()
    except IntegrityError:
        # A concurrent registration has the same neutral outcome as an existing account.
        pass
    await audit(
        session,
        action="register",
        resource_id_hash=hashlib.sha256(normalized.encode()).hexdigest(),
        result="success",
        request_id=request_id,
    )
    await session.commit()


async def login_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    request: Request,
    settings: Settings,
) -> IssuedSession:
    """Authenticate a user and issue one fresh server-side session."""

    check_write_origin(request, settings)
    normalized = normalize_email(email)
    request_id = getattr(request.state, "request_id", "unknown")
    await _limited(
        request,
        f"login:ip:{request.client.host if request.client else 'unknown'}",
        settings.auth_rate_limit_per_minute,
    )
    account_key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    await _limited(request, f"login:account:{account_key}", settings.auth_rate_limit_per_minute)
    user = (
        await session.execute(
            select(User).where(
                User.email_normalized == normalized,
                User.status == "active",
                User.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    password_hash = user.password_hash if user is not None else dummy_password_hash()
    password_matches = verify_password(password_hash, password)
    if user is None or not password_matches:
        await audit(
            session,
            action="login",
            resource_id_hash=hashlib.sha256(normalized.encode()).hexdigest(),
            result="failure",
            request_id=request_id,
        )
        await session.commit()
        raise AppError(status_code=401, code="invalid_credentials", message="邮箱或密码不正确")

    now = datetime.now(UTC)
    raw_token = opaque_token()
    csrf_token = opaque_token()
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=token_hash(raw_token),
        csrf_token_hash=token_hash(csrf_token),
        expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
        user_agent_hash=hashlib.sha256(
            request.headers.get("user-agent", "").encode("utf-8")
        ).hexdigest(),
    )
    user.last_login_at = now
    session.add(auth_session)
    await session.flush()
    await audit(
        session,
        action="login",
        resource_id_hash=hashlib.sha256(normalized.encode()).hexdigest(),
        result="success",
        request_id=request_id,
    )
    await session.commit()
    return IssuedSession(
        raw_token=raw_token,
        csrf_token=csrf_token,
        expires_at=auth_session.expires_at,
        user=user,
        session_id=auth_session.id,
    )


async def current_auth(session: AsyncSession, request: Request) -> tuple[User, AuthSession]:
    """Resolve a live session from the HttpOnly cookie."""

    raw_token = request.cookies.get(request.app.state.settings.session_cookie_name)
    if not raw_token:
        raise AppError(
            status_code=401,
            code="authentication_required",
            message="请先登录",
        )
    now = datetime.now(UTC)
    result = (
        await session.execute(
            select(User, AuthSession)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(
                AuthSession.token_hash == token_hash(raw_token),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
                User.status == "active",
                User.deleted_at.is_(None),
            )
        )
    ).first()
    if result is None:
        raise AppError(
            status_code=401,
            code="authentication_required",
            message="登录状态已失效，请重新登录",
        )
    user, auth_session = result
    auth_session.last_seen_at = now
    await session.flush()
    return user, auth_session


def verify_csrf(request: Request, settings: Settings, auth_session: AuthSession) -> None:
    """Require an explicit token plus an allowed request origin."""

    check_write_origin(request, settings)
    supplied = request.headers.get("X-CSRF-Token")
    if not supplied or not tokens_equal(token_hash(supplied), auth_session.csrf_token_hash):
        raise AppError(status_code=403, code="csrf_rejected", message="请求安全校验失败")


async def logout_user(
    session: AsyncSession,
    *,
    request: Request,
    settings: Settings,
) -> None:
    """Revoke the current session idempotently."""

    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        auth_session = (
            await session.execute(
                select(AuthSession).where(AuthSession.token_hash == token_hash(raw_token))
            )
        ).scalar_one_or_none()
        if auth_session is not None:
            verify_csrf(request, settings, auth_session)
            if auth_session.revoked_at is None:
                auth_session.revoked_at = datetime.now(UTC)
                await audit(
                    session,
                    action="logout",
                    resource_id_hash=hashlib.sha256(auth_session.user_id.bytes).hexdigest(),
                    result="success",
                    request_id=getattr(request.state, "request_id", "unknown"),
                )
                await session.commit()
            return
    check_write_origin(request, settings)


async def request_password_reset(
    session: AsyncSession,
    *,
    email: str,
    request: Request,
    settings: Settings,
) -> str | None:
    """Create a one-time reset token, returning it only to the mail adapter."""

    check_write_origin(request, settings)
    normalized = normalize_email(email)
    await _limited(
        request,
        f"reset:ip:{request.client.host if request.client else 'unknown'}",
        settings.auth_rate_limit_per_minute,
    )
    account_key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    await _limited(request, f"reset:account:{account_key}", settings.auth_rate_limit_per_minute)
    user = (
        await session.execute(
            select(User).where(
                User.email_normalized == normalized,
                User.status == "active",
                User.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    raw_token = None
    if user is not None:
        now = datetime.now(UTC)
        await session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        raw_token = opaque_token()
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash(raw_token),
                expires_at=now + timedelta(seconds=settings.password_reset_ttl_seconds),
            )
        )
    await audit(
        session,
        action="password_reset_request",
        resource_id_hash=hashlib.sha256(normalized.encode()).hexdigest(),
        result="success",
        request_id=getattr(request.state, "request_id", "unknown"),
    )
    await session.commit()
    return raw_token


async def confirm_password_reset(
    session: AsyncSession,
    *,
    token: str,
    new_password: str,
    request: Request,
    settings: Settings,
) -> None:
    """Consume a reset token, rotate the password, and revoke all sessions."""

    validate_password(new_password)
    check_write_origin(request, settings)
    now = datetime.now(UTC)
    reset = (
        await session.execute(
            select(PasswordResetToken)
            .where(
                PasswordResetToken.token_hash == token_hash(token),
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.revoked_at.is_(None),
                PasswordResetToken.expires_at > now,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if reset is None:
        raise AppError(
            status_code=410,
            code="reset_token_invalid",
            message="重置链接无效或已过期",
        )
    user = await session.get(User, reset.user_id)
    if user is None or user.status != "active":
        raise AppError(
            status_code=410,
            code="reset_token_invalid",
            message="重置链接无效或已过期",
        )
    user.password_hash = hash_password(new_password)
    reset.used_at = now
    await session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await audit(
        session,
        action="password_reset_confirm",
        resource_id_hash=hashlib.sha256(user.id.bytes).hexdigest(),
        result="success",
        request_id=getattr(request.state, "request_id", "unknown"),
    )
    await session.commit()
