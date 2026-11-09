"""认证与服务端会话生命周期。"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import Request
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.crypto import encrypt_secret
from app.db.jobs import enqueue_job
from app.db.models import AuthSession, PasswordResetToken, User
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
from app.services._audit import audit
from app.services._idempotency import sha256_text

logger = get_logger("app.auth")


def _is_unique_violation(exc: IntegrityError) -> bool:
    """仅识别 PostgreSQL 唯一约束冲突(23505),不把其他约束失败当并发注册。"""

    original = getattr(exc, "orig", None)
    sqlstate = getattr(original, "sqlstate", None)
    if sqlstate == "23505":
        return True
    constraint = getattr(getattr(original, "diag", None), "constraint_name", None)
    return isinstance(constraint, str) and constraint == "uq_users_email_normalized"


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """原始会话令牌与公开会话元数据。"""

    raw_token: str
    csrf_token: str
    expires_at: datetime
    user: User
    session_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class RoleChange:
    """为一个活跃账户执行可审计的角色转换。"""

    user_id: uuid.UUID
    previous_role: Literal["user", "admin"]
    current_role: Literal["user", "admin"]


async def set_user_role(
    session: AsyncSession,
    *,
    email: str,
    role: Literal["user", "admin"],
    request_id: str,
) -> RoleChange:
    """设置一个活跃账户的角色并持久化一条最小化审计事件。"""

    normalized = normalize_email(email)
    user = (
        await session.execute(
            select(User)
            .where(
                User.email_normalized == normalized,
                User.status == "active",
                User.deleted_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if user is None:
        raise AppError(status_code=404, code="resource_not_found", message="用户不存在")
    previous = user.role
    user.role = role
    await session.flush()
    await audit(
        session,
        action="user_role_changed",
        resource_id_hash=sha256_text(normalized),
        result="success",
        request_id=request_id,
    )
    return RoleChange(
        user_id=user.id,
        previous_role=previous,  # type: ignore[arg-type]
        current_role=role,
    )


async def _limited(request: Request, key: str, limit: int) -> None:
    """应用基于 Redis 的固定窗口限流器。"""

    bucket = f"auth:rate:{key}"
    redis = request.app.state.redis
    try:
        pipe = redis.pipeline(transaction=True)
        pipe.incr(bucket)
        pipe.expire(bucket, 60)
        count, _ = await pipe.execute()
    except (RedisError, RedisConnectionError, RedisTimeoutError, OSError) as exc:
        logger.warning("auth rate limiter unavailable", error_code=type(exc).__name__)
        raise AppError(
            status_code=503,
            code="service_unavailable",
            message="认证服务暂时不可用",
            retryable=True,
        ) from exc
    if count > limit:
        raise AppError(
            status_code=429,
            code="rate_limited",
            message="请求过于频繁，请稍后重试",
            retryable=True,
        )


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    request: Request,
    settings: Settings,
) -> None:
    """创建用户或返回相同的中性结果。"""

    validate_password(password)
    check_write_origin(request, settings)
    normalized = normalize_email(email)
    request_id = getattr(request.state, "request_id", "unknown")
    await _limited(
        request,
        f"register:ip:{request.client.host if request.client else 'unknown'}",
        settings.auth_rate_limit_per_minute,
    )
    account_key = sha256_text(normalized)
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
    except IntegrityError as exc:
        # 只有 email_normalized 唯一冲突才对应"账户已存在"的中性结果;
        # 其他约束失败必须上抛,不能静默返回 202。
        if not _is_unique_violation(exc):
            raise
    await audit(
        session,
        action="register",
        resource_id_hash=sha256_text(normalized),
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
    """认证用户并签发一个全新的服务端会话。"""

    check_write_origin(request, settings)
    normalized = normalize_email(email)
    request_id = getattr(request.state, "request_id", "unknown")
    await _limited(
        request,
        f"login:ip:{request.client.host if request.client else 'unknown'}",
        settings.auth_rate_limit_per_minute,
    )
    account_key = sha256_text(normalized)
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
            resource_id_hash=sha256_text(normalized),
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
        resource_id_hash=sha256_text(normalized),
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
    """从 HttpOnly cookie 中解析出有效会话。"""

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


async def current_auth_for_deletion_status(
    session: AsyncSession,
    request: Request,
) -> tuple[User, AuthSession]:
    """账户匿名化后仅允许删除状态端点读取。"""

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
                User.status.in_(("active", "deleted")),
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
    """要求显式令牌以及允许的请求来源。"""

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
    """幂等地撤销当前会话。"""

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
    """创建一次性重置令牌并将中性链接投递入队。"""

    check_write_origin(request, settings)
    normalized = normalize_email(email)
    await _limited(
        request,
        f"reset:ip:{request.client.host if request.client else 'unknown'}",
        settings.auth_rate_limit_per_minute,
    )
    account_key = sha256_text(normalized)
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
        reset = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash(raw_token),
            expires_at=now + timedelta(seconds=settings.password_reset_ttl_seconds),
        )
        session.add(reset)
        await session.flush()
        reset.delivery_ciphertext = encrypt_secret(
            settings,
            f"{normalized}\0{raw_token}",
        )
        await enqueue_job(
            session,
            owner_user_id=user.id,
            job_type="password_reset_delivery",
            resource_type="password_reset_token",
            resource_id=reset.id,
            idempotency_key=f"password-reset-delivery:{reset.id.hex}",
            max_attempts=settings.worker_max_attempts,
        )
    await audit(
        session,
        action="password_reset_request",
        resource_id_hash=sha256_text(normalized),
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
    """消费重置令牌,轮换密码,并撤销所有会话。"""

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
