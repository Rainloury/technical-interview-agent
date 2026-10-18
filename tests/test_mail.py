"""Password reset delivery adapter behavior."""

from __future__ import annotations

import smtplib

import pytest
from app.config import Settings
from app.mail import deliver_password_reset


@pytest.mark.asyncio
async def test_production_smtp_failure_is_not_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        app_env="production",
        smtp_host="smtp.example.com",
        smtp_from_email="no-reply@example.com",
    )

    def fail(*_: object, **__: object) -> None:
        raise OSError("smtp unavailable")

    monkeypatch.setattr("app.mail._send_smtp", fail)

    with pytest.raises(OSError, match="smtp unavailable"):
        await deliver_password_reset(settings, email="user@example.com", token="token")


@pytest.mark.asyncio
async def test_development_smtp_failure_keeps_neutral_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        app_env="development",
        smtp_host="smtp.example.com",
        smtp_from_email="no-reply@example.com",
    )

    def fail(*_: object, **__: object) -> None:
        raise OSError("smtp unavailable")

    monkeypatch.setattr("app.mail._send_smtp", fail)

    await deliver_password_reset(settings, email="user@example.com", token="token")


def test_directmail_ssl_mode_uses_smtp_ssl(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import mail

    settings = Settings(
        app_env="production",
        smtp_host="smtpdm.aliyun.com",
        smtp_port=465,
        smtp_security="ssl",
        smtp_from_email="no-reply@example.com",
        smtp_username="user",
        smtp_password="password",
    )
    used: list[tuple[int, bool]] = []

    class FakeSmtp:
        def __init__(self, host: str, port: int, **_: object) -> None:
            assert host == "smtpdm.aliyun.com"
            used.append((port, True))

        def __enter__(self) -> FakeSmtp:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def login(self, *_: object) -> None:
            return None

        def send_message(self, *_: object) -> None:
            return None

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    mail._send_smtp(settings, "user@example.com", "https://example.com/reset")

    assert used == [(465, True)]
