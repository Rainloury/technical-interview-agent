"""密码、不透明令牌和请求来源安全原语。"""

from __future__ import annotations

import hashlib
import secrets
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Request

from app.config import Settings
from app.errors import AppError

_PASSWORD_HASHER = PasswordHasher()
_DUMMY_PASSWORD_HASH = _PASSWORD_HASHER.hash("not-a-real-user-password")


def normalize_email(email: str) -> str:
    """在唯一性检查和查找前一致地规范化电子邮件。"""

    return unicodedata.normalize("NFKC", email).strip().lower()


def validate_password(password: str) -> None:
    """应用共享密码策略且不回显输入。"""

    if len(password) < 12 or len(password) > 128:
        raise AppError(
            status_code=422,
            code="invalid_request",
            message="密码长度需为 12 至 128 个字符",
        )


def hash_password(password: str) -> str:
    """使用 Argon2id 哈希密码。"""

    return _PASSWORD_HASHER.hash(password)


def dummy_password_hash() -> str:
    """返回用于均衡失败账户查找的稳定哈希。"""

    return _DUMMY_PASSWORD_HASH


def verify_password(password_hash: str, password: str) -> bool:
    """在不依赖哈希可用性的情况下校验密码。"""

    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def opaque_token() -> str:
    """生成不透明高熵令牌。"""

    return secrets.token_urlsafe(48)


def token_hash(token: str) -> str:
    """在持久化前哈希 bearer 或 CSRF 令牌。"""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_equal(left: str, right: str) -> bool:
    """以常量时间比较验证字符串。"""

    return secrets.compare_digest(left, right)


@dataclass(frozen=True, slots=True)
class RequestOrigin:
    """已解析的同源请求元数据。"""

    scheme: str
    host: str


def request_origin(request: Request) -> RequestOrigin | None:
    """返回 Origin 头或从 Referer 派生一个。"""

    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
    else:
        referer = request.headers.get("referer")
        if not referer:
            return None
        parsed = urlsplit(referer)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return RequestOrigin(scheme=parsed.scheme, host=parsed.netloc)


def check_write_origin(request: Request, settings: Settings) -> None:
    """在 CSRF 验证之前拒绝跨源写入。"""

    origin = request_origin(request)
    if origin is None:
        raise AppError(
            status_code=403,
            code="csrf_rejected",
            message="请求来源校验失败",
        )
    normalized = f"{origin.scheme}://{origin.host}"
    if normalized not in settings.csrf_allowed_origins:
        raise AppError(
            status_code=403,
            code="csrf_rejected",
            message="请求来源校验失败",
        )
