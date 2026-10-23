"""Alert evaluation, webhook delivery, and worker heartbeat tests."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from app.alerts import (
    AlertObservation,
    database_observations,
    deliver_alerts,
    readiness_observation,
    worker_heartbeat_observation,
)
from app.config import Settings
from app.db.models import (
    AlertDelivery,
    AsyncJob,
    DataDeletionRequest,
    Interview,
    InterviewTurn,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _settings(tmp_path: Path, **values: object) -> Settings:
    return Settings(
        app_env="test",
        alert_webhook_url="https://alerts.example.test/hook",
        worker_health_file=str(tmp_path / "worker-health.json"),
        _env_file=None,
        **values,
    )


def test_worker_heartbeat_alerts_when_missing_or_stale(tmp_path: Path) -> None:
    health = tmp_path / "worker-health.json"
    missing = worker_heartbeat_observation(health, max_age_seconds=90, now=100)
    assert missing is not None
    assert missing.code == "worker_heartbeat_stale"

    health.write_text('{"state":"running"}', encoding="utf-8")
    os.utime(health, (10, 10))
    stale = worker_heartbeat_observation(health, max_age_seconds=10, now=100)
    assert stale is not None
    assert stale.observed_count == 1
    assert worker_heartbeat_observation(health, max_age_seconds=90, now=20) is None


async def test_readiness_alert_handles_degraded_and_transport_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health/ready"
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        degraded = await readiness_observation(
            api_base_url="https://api.example.test",
            request_timeout=1,
            client=client,
        )
    assert degraded is not None
    assert degraded.code == "ready_failed"

    async def failing(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    async with httpx.AsyncClient(transport=httpx.MockTransport(failing)) as client:
        failed = await readiness_observation(
            api_base_url="https://api.example.test",
            request_timeout=1,
            client=client,
        )
    assert failed is not None
    assert "HTTP 0" in failed.message


@pytest.mark.integration
async def test_database_observations_cover_dead_letter_scoring_and_deletion(
    db_session: AsyncSession,
    create_user: object,
) -> None:
    user_factory = create_user
    user = user_factory(email="alerts@example.test")  # type: ignore[operator]
    db_session.add(user)
    await db_session.flush()
    interview = Interview(
        owner_user_id=user.id,
        direction="backend",
        difficulty_profile={},
        topic_keys={},
        state="in_progress",
        total_token_budget=100,
        blueprint_version="test",
        scoring_version="test",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(interview)
    await db_session.flush()
    turn = InterviewTurn(
        interview_id=interview.id,
        owner_user_id=user.id,
        root_turn_id=interview.id,
        turn_type="main",
        depth=0,
        state="scoring_failed",
        sequence=1,
        question_text="question",
        reference_answer="reference",
        scoring_rubric={},
        topic_key="topic",
        difficulty="easy",
        question_snapshot={},
    )
    db_session.add(turn)
    await db_session.flush()
    db_session.add(
        AsyncJob(
            owner_user_id=user.id,
            job_type="delete_data",
            resource_type="resume_task",
            resource_id=turn.id,
            idempotency_key="alerts-dead-letter",
            state="dead_letter",
            max_attempts=3,
        )
    )
    db_session.add(
        DataDeletionRequest(
            owner_user_id=user.id,
            idempotency_key="alerts-deletion",
            request_fingerprint="fingerprint",
            state="failed",
            scope={},
        )
    )
    await db_session.commit()

    observations = await database_observations(db_session)
    by_code = {observation.code: observation for observation in observations}
    assert by_code["dead_letter"].observed_count == 1
    assert by_code["scoring_failed"].observed_count == 1
    assert by_code["deletion_failed"].observed_count == 1


@pytest.mark.integration
async def test_webhook_delivery_records_success_and_failure(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    observations = [
        AlertObservation("dead_letter", "critical", 2, "two jobs"),
        AlertObservation("ready_failed", "critical", 1, "ready failed"),
    ]
    calls: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.headers))
        return httpx.Response(204 if len(calls) == 1 else 500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        deliveries = await deliver_alerts(
            session=db_session,
            settings=settings,
            observations=observations,
            client=client,
        )

    assert [delivery.status for delivery in deliveries] == ["delivered", "failed"]
    assert deliveries[1].http_status == 500
    assert all(call["content-type"] == "application/json" for call in calls)
    rows = list(
        (
            await db_session.execute(select(AlertDelivery).order_by(AlertDelivery.created_at))
        ).scalars()
    )
    assert len(rows) == 2
