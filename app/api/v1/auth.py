"""账户和会话生命周期的 HTTP 边界。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request, Response, status

from app.api.dependencies import AuthDependency, SessionDependency
from app.config import Settings
from app.schemas.auth import (
    EmailRequest,
    LoginResponse,
    PasswordRequest,
    PasswordResetConfirm,
    RegisterAccepted,
    SessionResponse,
    SessionSummary,
    UserSummary,
)
from app.services.auth import (
    confirm_password_reset,
    login_user,
    logout_user,
    register_user,
    request_password_reset,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookies(
    response: Response,
    *,
    settings: Settings,
    session_token: str,
    csrf_token: str,
    expires_at: datetime,
) -> None:
    """设置 HttpOnly 会话 cookie 和可读的 CSRF 验证 cookie。"""

    secure = settings.cookie_secure
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        expires=expires_at,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
        expires=expires_at,
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    """在登出或密码重置后使两个 cookie 过期。"""

    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
async def register(
    payload: PasswordRequest,
    request: Request,
    session: SessionDependency,
) -> RegisterAccepted:
    """创建账户或返回相同的中性接受响应。"""

    await register_user(
        session,
        email=payload.email,
        password=payload.password,
        request=request,
        settings=request.app.state.settings,
    )
    return RegisterAccepted()


@router.post("/login")
async def login(
    payload: PasswordRequest,
    request: Request,
    response: Response,
    session: SessionDependency,
) -> LoginResponse:
    """验证凭据并签发全新的服务端会话。"""

    issued = await login_user(
        session,
        email=payload.email,
        password=payload.password,
        request=request,
        settings=request.app.state.settings,
    )
    _set_session_cookies(
        response,
        settings=request.app.state.settings,
        session_token=issued.raw_token,
        csrf_token=issued.csrf_token,
        expires_at=issued.expires_at,
    )
    return LoginResponse(
        user=UserSummary(
            id=issued.user.id,
            display_name=issued.user.display_name,
            role=issued.user.role,
        ),
        session=SessionSummary(expires_at=issued.expires_at),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: SessionDependency,
) -> Response:
    """撤销当前会话并使客户端 cookie 过期。"""

    await logout_user(
        session,
        request=request,
        settings=request.app.state.settings,
    )
    _clear_auth_cookies(response, request.app.state.settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/session")
async def read_session(auth: AuthDependency) -> SessionResponse:
    """仅返回安全的用户和过期元数据。"""

    return SessionResponse(
        user=UserSummary(
            id=auth.user.id,
            display_name=auth.user.display_name,
            role=auth.user.role,
        ),
        session=SessionSummary(expires_at=auth.session.expires_at),
    )


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_reset(
    payload: EmailRequest,
    request: Request,
    session: SessionDependency,
) -> dict[str, bool]:
    """无论账户是否存在都返回中性接受响应。"""

    await request_password_reset(
        session,
        email=payload.email,
        request=request,
        settings=request.app.state.settings,
    )
    return {"accepted": True}


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_reset(
    payload: PasswordResetConfirm,
    request: Request,
    response: Response,
    session: SessionDependency,
) -> Response:
    """轮换密码、撤销旧会话并清除认证 cookie。"""

    await confirm_password_reset(
        session,
        token=payload.token,
        new_password=payload.new_password,
        request=request,
        settings=request.app.state.settings,
    )
    _clear_auth_cookies(response, request.app.state.settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
