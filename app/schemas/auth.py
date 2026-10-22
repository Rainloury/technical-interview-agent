"""Authentication DTOs."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.security import normalize_email


class EmailRequest(BaseModel):
    """Request containing a normalized email address."""

    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def normalize(cls, value: str) -> str:
        normalized = normalize_email(value)
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("invalid email")
        return normalized


class PasswordRequest(EmailRequest):
    """Request containing credentials."""

    password: str = Field(min_length=12, max_length=128)


class PasswordResetConfirm(BaseModel):
    """Request containing a one-time reset token and a new password."""

    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)


class NeutralAccepted(BaseModel):
    """Non-enumerating acceptance payload."""

    accepted: Literal[True] = True


class RegisterAccepted(NeutralAccepted):
    """Registration acceptance that never reveals account existence."""

    next_action: Literal["login"] = "login"


class UserSummary(BaseModel):
    """Safe public user fields."""

    id: UUID
    display_name: str | None
    role: Literal["user", "admin"]


class SessionSummary(BaseModel):
    """Safe public session fields."""

    expires_at: datetime


class LoginResponse(BaseModel):
    """Successful login payload."""

    user: UserSummary
    session: SessionSummary


class SessionResponse(BaseModel):
    """Current-session payload."""

    user: UserSummary
    session: SessionSummary
