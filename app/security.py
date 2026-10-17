"""Password, opaque-token, and request-origin security primitives."""

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
    """Normalize an email consistently before uniqueness and lookup."""

    return unicodedata.normalize("NFKC", email).strip().lower()


def validate_password(password: str) -> None:
    """Apply the shared password policy without echoing the input."""

    if len(password) < 12 or len(password) > 128:
        raise AppError(
            status_code=422,
            code="invalid_request",
            message="密码长度需为 12 至 128 个字符",
        )


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""

    return _PASSWORD_HASHER.hash(password)


def dummy_password_hash() -> str:
    """Return a stable hash used to equalize failed account lookups."""

    return _DUMMY_PASSWORD_HASH


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a password without depending on hash availability."""

    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def opaque_token() -> str:
    """Generate an opaque high-entropy token."""

    return secrets.token_urlsafe(48)


def token_hash(token: str) -> str:
    """Hash a bearer or CSRF token before persistence."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_equal(left: str, right: str) -> bool:
    """Compare verifier strings in constant time."""

    return secrets.compare_digest(left, right)


@dataclass(frozen=True, slots=True)
class RequestOrigin:
    """Parsed same-origin request metadata."""

    scheme: str
    host: str


def request_origin(request: Request) -> RequestOrigin | None:
    """Return the Origin header or derive one from Referer."""

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
    """Reject cross-origin writes before CSRF verification."""

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
