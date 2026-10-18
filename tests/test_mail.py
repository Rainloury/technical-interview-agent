"""Password reset delivery adapter behavior."""

from __future__ import annotations

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
