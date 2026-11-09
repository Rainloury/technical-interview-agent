"""service 层异常与幂等边界的回归测试。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import pytest
from app.db.jobs import enqueue_job
from app.db.models import AsyncJob, QaRequest, QaStreamEvent
from app.services.auth import _limited, register_user
from app.services.qa import QaContractError, append_event, completion_payload
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import AppHarness

pytestmark = pytest.mark.integration


async def test_enqueue_job_returns_existing_row_on_unique_conflict(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    owner = create_user("enqueue-owner@example.com")
    async with app_client.session_factory() as session:
        session.add(owner)
        await session.commit()

    key = f"concurrent-enqueue:{uuid.uuid4().hex}"
    resource_id = uuid.uuid4()

    async def enqueue() -> None:
        async with app_client.session_factory() as session:
            await enqueue_job(
                session,
                owner_user_id=owner.id,
                job_type="parse_resume",
                resource_type="resume_task",
                resource_id=resource_id,
                idempotency_key=key,
                max_attempts=3,
            )
            await session.commit()

    await asyncio.gather(enqueue(), enqueue())

    async with app_client.session_factory() as session:
        rows = list(
            (
                await session.execute(select(AsyncJob).where(AsyncJob.idempotency_key == key))
            ).scalars()
        )
    assert len(rows) == 1


async def test_qa_terminal_conflict_uses_non_retryable_contract_error(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    owner = create_user("qa-contract@example.com")
    async with app_client.session_factory() as session:
        session.add(owner)
        await session.flush()
        request = QaRequest(
            owner_user_id=owner.id,
            question_text="问题",
            answer_preference="concise",
            state="failed",
            model_name="DEFAULT",
            prompt_version="1.1.0",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        session.add(request)
        await session.flush()
        session.add(
            QaStreamEvent(qa_request_id=request.id, seq=1, event_type="error", payload_json={})
        )
        await session.commit()
        request_id = request.id

    async with app_client.session_factory() as session:
        persisted = await session.get(QaRequest, request_id)
        assert persisted is not None
        with pytest.raises(QaContractError) as exc_info:
            await append_event(session, persisted, event_type="error", payload={})
    assert exc_info.value.code == "qa_terminal_conflict"

    with pytest.raises(QaContractError) as missing:
        completion_payload(
            QaRequest(state="completed", answer_json=None),
            [],
        )
    assert missing.value.code == "qa_answer_missing"


async def test_register_does_not_swallow_non_unique_integrity_errors(
    app_client: AppHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyRequest:
        app = app_client.app
        state = type("State", (), {"request_id": "test-request"})()
        client = None
        headers: ClassVar[dict[str, str]] = {}

    def fake_check_write_origin(request: Any, settings: Any) -> None:
        del request, settings

    monkeypatch.setattr("app.services.auth.check_write_origin", fake_check_write_origin)

    class FailingSession(AsyncSession):
        def begin_nested(self) -> Any:
            raise IntegrityError("INSERT", {}, Exception("check constraint violated"))

    async with FailingSession(bind=app_client.write_engine) as session:
        with pytest.raises(IntegrityError):
            await register_user(
                session,
                email="new@example.com",
                password="correct horse battery staple",
                request=DummyRequest(),  # type: ignore[arg-type]
                settings=app_client.app.state.settings,
            )


async def test_auth_rate_limit_sets_expiration_atomically(
    app_client: AppHarness,
) -> None:
    class DummyRequest:
        app = app_client.app

    await _limited(DummyRequest(), "atomic-key", 5)  # type: ignore[arg-type]
    assert app_client.app.state.redis.expirations["auth:rate:atomic-key"] == 60
