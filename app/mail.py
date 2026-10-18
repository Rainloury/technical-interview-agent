"""Minimal password-reset delivery adapter."""

from __future__ import annotations

import asyncio
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from app.config import Settings
from app.logging import get_logger

logger = get_logger("app.mail")


def _write_local_reset(path: Path, email: str, reset_url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"email": email, "reset_url": reset_url}, ensure_ascii=False),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def _send_smtp(settings: Settings, email: str, reset_url: str) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        return
    message = EmailMessage()
    message["Subject"] = "重置 Technical Interview Agent 密码"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(f"请在有效期内打开以下链接重置密码：\n\n{reset_url}\n")
    if settings.smtp_security == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=10,
            context=ssl.create_default_context(),
        )
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
    with client:
        if settings.smtp_security == "starttls":
            client.starttls(context=ssl.create_default_context())
        if settings.smtp_username and settings.smtp_password:
            client.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        client.send_message(message)


async def deliver_password_reset(settings: Settings, *, email: str, token: str | None) -> None:
    """Deliver a reset link without exposing delivery state to API callers."""

    if token is None:
        return
    reset_url = f"{settings.password_reset_base_url}?token={token}"
    if settings.app_env == "development" and not settings.smtp_host:
        await asyncio.to_thread(
            _write_local_reset,
            Path(settings.mail_local_reset_file),
            email,
            reset_url,
        )
        logger.info("password reset written to local development sink")
        return
    if settings.smtp_host:
        try:
            await asyncio.to_thread(_send_smtp, settings, email, reset_url)
        except Exception as exc:
            logger.warning("password reset delivery failed", error_code=type(exc).__name__)
            if settings.app_env in {"staging", "production"}:
                raise
