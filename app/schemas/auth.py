"""认证 DTO。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.security import normalize_email


class EmailRequest(BaseModel):
    """包含规范化电子邮件地址的请求。"""

    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def normalize(cls, value: str) -> str:
        normalized = normalize_email(value)
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("invalid email")
        return normalized


class PasswordRequest(EmailRequest):
    """包含凭据的请求。"""

    password: str = Field(min_length=12, max_length=128)


class PasswordResetConfirm(BaseModel):
    """包含一次性重置令牌和新密码的请求。"""

    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)


class NeutralAccepted(BaseModel):
    """非枚举接受载荷。"""

    accepted: Literal[True] = True


class RegisterAccepted(NeutralAccepted):
    """从不泄露账户存在性的注册接受。"""

    next_action: Literal["login"] = "login"


class UserSummary(BaseModel):
    """安全的公开用户字段。"""

    id: UUID
    display_name: str | None
    role: Literal["user", "admin"]


class SessionSummary(BaseModel):
    """安全的公开会话字段。"""

    expires_at: datetime


class LoginResponse(BaseModel):
    """成功登录载荷。"""

    user: UserSummary
    session: SessionSummary


class SessionResponse(BaseModel):
    """当前会话载荷。"""

    user: UserSummary
    session: SessionSummary
