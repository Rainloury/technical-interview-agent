"""Database contract and concurrency tests."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.config import Settings
from app.db.jobs import finish_job, lease_next_job, renew_job_lease
from app.db.models import AsyncJob, Interview, QaRequest, QaStreamEvent, User
from app.db.session import create_engine, create_session_factory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def _user(session: AsyncSession) -> User:
    user = User(
        email_normalized=f"{uuid.uuid4()}@example.com",
        password_hash="not-used",
    )
    session.add(user)
    await session.flush()
    return user


async def _qa_request(session: AsyncSession, user: User) -> QaRequest:
    request = QaRequest(
        owner_user_id=user.id,
        question_text="What is a database transaction?",
        model_name="test-model",
        prompt_version="test-v1",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    session.add(request)
    await session.flush()
    return request


async def test_transaction_fixture_rolls_back(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    await db_session.flush()
    assert user.id is not None


async def test_qa_stream_sequence_is_unique_per_request(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    request = await _qa_request(db_session, user)
    db_session.add(
        QaStreamEvent(
            qa_request_id=request.id,
            seq=1,
            event_type="started",
            payload_json={},
        )
    )
    await db_session.flush()
    db_session.add(
        QaStreamEvent(
            qa_request_id=request.id,
            seq=1,
            event_type="delta",
            payload_json={"text": "duplicate"},
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.parametrize("terminal", ["completed", "error"])
async def test_terminal_event_is_unique_per_request(
    db_session: AsyncSession, terminal: str
) -> None:
    user = await _user(db_session)
    request = await _qa_request(db_session, user)
    db_session.add(
        QaStreamEvent(
            qa_request_id=request.id,
            seq=1,
            event_type=terminal,
            payload_json={},
        )
    )
    await db_session.flush()
    db_session.add(
        QaStreamEvent(
            qa_request_id=request.id,
            seq=2,
            event_type=terminal,
            payload_json={},
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_job_lease_increments_fencing_and_rejects_stale_writes(
    db_session: AsyncSession,
) -> None:
    job = AsyncJob(
        job_type="parse_resume",
        resource_type="resume_task",
        resource_id=uuid.uuid4(),
        idempotency_key=str(uuid.uuid4()),
        max_attempts=3,
        next_run_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    db_session.add(job)
    await db_session.flush()

    first = await lease_next_job(
        db_session,
        worker_id="worker-a",
        allowed_job_ids=(job.id,),
    )
    assert first is not None
    assert first.id == job.id
    assert first.fencing_token == 1
    assert first.attempt_count == 1
    first_token = first.fencing_token

    assert await finish_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        fencing_token=first_token,
        state="failed",
        next_run_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    await db_session.flush()
    second = await lease_next_job(
        db_session,
        worker_id="worker-b",
        allowed_job_ids=(job.id,),
    )
    assert second is not None
    assert second.fencing_token == 2

    assert not await finish_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        fencing_token=first_token,
        state="succeeded",
    )
    assert not await renew_job_lease(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        fencing_token=first_token,
    )
    assert await finish_job(
        db_session,
        job_id=job.id,
        worker_id="worker-b",
        fencing_token=second.fencing_token,
        state="succeeded",
    )


async def test_expired_lease_can_be_reclaimed(db_session: AsyncSession) -> None:
    job = AsyncJob(
        job_type="parse_resume",
        resource_type="resume_task",
        resource_id=uuid.uuid4(),
        idempotency_key=str(uuid.uuid4()),
        max_attempts=3,
        next_run_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    db_session.add(job)
    await db_session.flush()

    first = await lease_next_job(
        db_session,
        worker_id="worker-a",
        lease_seconds=1,
        allowed_job_ids=(job.id,),
    )
    assert first is not None
    await db_session.execute(
        text(
            "UPDATE async_jobs "
            "SET lease_until = statement_timestamp() - interval '1 second' "
            "WHERE id = :id"
        ),
        {"id": job.id},
    )
    await db_session.flush()
    second = await lease_next_job(
        db_session,
        worker_id="worker-b",
        allowed_job_ids=(job.id,),
    )
    assert second is not None
    assert second.fencing_token == 2


async def test_concurrent_workers_lease_one_job_once(settings: Settings) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    job_id = uuid.uuid4()
    try:
        async with factory() as setup:
            setup.add(
                AsyncJob(
                    id=job_id,
                    job_type="parse_resume",
                    resource_type="resume_task",
                    resource_id=uuid.uuid4(),
                    idempotency_key=str(uuid.uuid4()),
                    max_attempts=3,
                    next_run_at=datetime.now(UTC) - timedelta(seconds=1),
                )
            )
            await setup.commit()

        async with factory() as first, factory() as second:
            first_claim = await lease_next_job(
                first,
                worker_id="worker-a",
                allowed_job_ids=(job_id,),
            )
            second_claim = await lease_next_job(
                second,
                worker_id="worker-b",
                allowed_job_ids=(job_id,),
            )

            assert first_claim is not None
            assert first_claim.id == job_id
            assert first_claim.lease_owner == "worker-a"
            assert first_claim.fencing_token == 1
            assert second_claim is None
            await first.commit()

        async with factory() as verify:
            claimed = await verify.get(AsyncJob, job_id)
            assert claimed is not None
            assert claimed.lease_owner == "worker-a"
            assert claimed.fencing_token == 1
            assert claimed.lease_until is not None
    finally:
        async with factory() as cleanup:
            await cleanup.execute(text("DELETE FROM async_jobs WHERE id = :id"), {"id": job_id})
            await cleanup.commit()
        await engine.dispose()


async def test_database_clock_deadline_boundaries(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    interview = Interview(
        owner_user_id=user.id,
        direction="backend",
        difficulty_profile={},
        topic_keys={},
        total_token_budget=1000,
        blueprint_version="v1",
        scoring_version="v1",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(interview)
    await db_session.flush()

    for offset, expected in ((1, True), (0, False), (-1, False)):
        await db_session.execute(
            text(
                "UPDATE interviews "
                "SET state = 'in_progress', "
                "started_at = statement_timestamp(), "
                "deadline_at = statement_timestamp() + make_interval(secs => :offset) "
                "WHERE id = :id"
            ),
            {"offset": offset, "id": interview.id},
        )
        valid = (
            await db_session.execute(
                text("SELECT statement_timestamp() < deadline_at FROM interviews WHERE id = :id"),
                {"id": interview.id},
            )
        ).scalar_one()
        assert valid is expected


async def test_audit_retention_constraint_is_enforced(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO audit_events "
                "(id, action, resource_type, resource_id_hash, result, request_id, "
                "created_at, expires_at) "
                "VALUES (:id, 'test', 'interview', 'hash', 'success', 'req_audit', "
                "statement_timestamp(), statement_timestamp() + interval '1 day')"
            ),
            {"id": uuid.uuid4()},
        )
    await db_session.rollback()
