"""Worker retry and terminal behavior for password-reset delivery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.config import Settings
from app.crypto import encrypt_secret
from app.db.models import AsyncJob, PasswordResetToken, User
from app.prompts.loader import PromptLoader
from app.worker import ResumeWorker
from sqlalchemy import select, text

from tests.conftest import AppHarness

pytestmark = pytest.mark.integration


def _worker(app_client: AppHarness, worker_id: str) -> ResumeWorker:
    settings = app_client.app.state.settings.model_copy(
        update={
            "worker_retry_base_seconds": 1,
            "worker_retry_max_seconds": 1,
            "worker_max_attempts": 2,
        }
    )
    return ResumeWorker(
        settings=settings,
        session_factory=app_client.session_factory,
        storage=app_client.app.state.resume_storage,
        llm=object(),  # type: ignore[arg-type]
        prompt_loader=PromptLoader(settings.prompt_dir),
        worker_id=worker_id,
    )


async def _queued_reset(
    app_client: AppHarness,
    *,
    email: str,
) -> tuple[User, PasswordResetToken]:
    settings = app_client.app.state.settings
    user = User(email_normalized=email, password_hash="not-used")
    async with app_client.session_factory() as session:
        session.add(user)
        await session.flush()
        reset = PasswordResetToken(
            user_id=user.id,
            token_hash=f"hash-{email}",
            delivery_ciphertext=encrypt_secret(settings, f"{email}\0reset-token"),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        session.add(reset)
        await session.flush()
        session.add(
            AsyncJob(
                owner_user_id=user.id,
                job_type="password_reset_delivery",
                resource_type="password_reset_token",
                resource_id=reset.id,
                idempotency_key=f"password-reset-delivery:{reset.id.hex}",
                max_attempts=2,
            )
        )
        await session.commit()
        return user, reset


async def test_password_reset_delivery_retries_then_succeeds(
    app_client: AppHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, reset = await _queued_reset(app_client, email="retry-reset@example.com")
    attempts = 0

    async def flaky(settings: Settings, *, email: str, token: str) -> None:
        nonlocal attempts
        del settings
        attempts += 1
        assert email == "retry-reset@example.com"
        assert token == "reset-token"
        if attempts == 1:
            raise OSError("smtp temporarily unavailable")

    monkeypatch.setattr("app.worker.deliver_password_reset", flaky)

    first = await _worker(app_client, "reset-retry-1").run_once()
    assert first.outcome == "retry_scheduled"

    async with app_client.session_factory() as session:
        await session.execute(
            text(
                "UPDATE async_jobs SET next_run_at = statement_timestamp() WHERE resource_id = :id"
            ),
            {"id": reset.id},
        )
        await session.commit()

    second = await _worker(app_client, "reset-retry-2").run_once()
    assert second.outcome == "succeeded"

    async with app_client.session_factory() as session:
        job = (
            await session.execute(select(AsyncJob).where(AsyncJob.resource_id == reset.id))
        ).scalar_one()
        stored = await session.get(PasswordResetToken, reset.id)
    assert job.state == "succeeded"
    assert stored is not None
    assert stored.delivery_ciphertext is None
    assert user.id == stored.user_id


async def test_password_reset_delivery_dead_letter_clears_ciphertext(
    app_client: AppHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _user, reset = await _queued_reset(app_client, email="dead-reset@example.com")

    async def fail(settings: Settings, *, email: str, token: str) -> None:
        del settings, email, token
        raise OSError("smtp unavailable")

    monkeypatch.setattr("app.worker.deliver_password_reset", fail)

    first = await _worker(app_client, "reset-dead-1").run_once()
    async with app_client.session_factory() as session:
        await session.execute(
            text(
                "UPDATE async_jobs SET next_run_at = statement_timestamp() WHERE resource_id = :id"
            ),
            {"id": reset.id},
        )
        await session.commit()
    second = await _worker(app_client, "reset-dead-2").run_once()
    assert first.outcome == "retry_scheduled"
    assert second.outcome == "dead_letter"

    async with app_client.session_factory() as session:
        job = (
            await session.execute(select(AsyncJob).where(AsyncJob.resource_id == reset.id))
        ).scalar_one()
        stored = await session.get(PasswordResetToken, reset.id)
    assert job.state == "dead_letter"
    assert stored is not None
    assert stored.delivery_ciphertext is None
