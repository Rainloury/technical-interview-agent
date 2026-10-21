"""Account data deletion, retention cleanup, and privacy audit integration tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.config import Settings
from app.db.models import (
    AsyncJob,
    AuditEvent,
    DataDeletionRequest,
    Interview,
    QaRequest,
    ResumeFile,
    ResumeTask,
    User,
    UserDocument,
    UserDocumentChunk,
)
from app.llm.models import ModelTier
from app.prompts.loader import PromptLoader
from app.storage import LocalPrivateStorage
from app.worker import ResumeWorker
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import AppHarness
from tests.test_account_api import _login, _write_headers

pytestmark = pytest.mark.integration


def _headers(client: TestClient, key: str | None = None) -> dict[str, str]:
    return {
        **_write_headers(client),
        "Idempotency-Key": key or str(uuid.uuid4()),
    }


async def _owner(app_client: AppHarness, create_user: Any, email: str) -> User:
    user: User = create_user(email)
    async with app_client.session_factory() as session:
        session.add(user)
        await session.commit()
    return user


class UnusedLlm:
    """Deletion jobs must never call the model."""

    async def generate(self, **_: Any) -> Any:
        raise AssertionError(f"model should not be called, tier={ModelTier.DEFAULT}")


def _worker(app_client: AppHarness, settings: Settings) -> ResumeWorker:
    return ResumeWorker(
        settings=settings,
        session_factory=app_client.session_factory,
        storage=LocalPrivateStorage(settings.resume_storage_dir),
        llm=UnusedLlm(),
        prompt_loader=PromptLoader("app/prompts"),
        worker_id=f"privacy-worker-{uuid.uuid4().hex[:6]}",
    )


async def _seed_business_data(
    app_client: AppHarness,
    settings: Settings,
    user: User,
) -> tuple[ResumeTask, QaRequest, Interview]:
    storage = LocalPrivateStorage(settings.resume_storage_dir)
    object_key = f"{user.id.hex}/private-resume.pdf"
    await storage.put(object_key, b"private resume bytes")
    now = datetime.now(UTC)
    async with app_client.session_factory() as session:
        task = ResumeTask(
            owner_user_id=user.id,
            state="completed",
            completed_at=now,
            expires_at=now + timedelta(days=90),
        )
        session.add(task)
        await session.flush()
        source = ResumeFile(
            resume_task_id=task.id,
            owner_user_id=user.id,
            original_filename="private-resume.pdf",
            declared_mime="application/pdf",
            detected_mime="application/pdf",
            size_bytes=20,
            sha256="f" * 64,
            object_key=object_key,
            storage_state="stored",
            retention_expires_at=now + timedelta(days=30),
        )
        qa = QaRequest(
            owner_user_id=user.id,
            question_text="private question",
            state="completed",
            model_name="test",
            prompt_version="v1",
            completed_at=now,
            expires_at=now + timedelta(days=90),
        )
        interview = Interview(
            owner_user_id=user.id,
            direction="backend",
            difficulty_profile={},
            topic_keys={},
            state="completed",
            total_token_budget=1000,
            blueprint_version="v1",
            scoring_version="v1",
            ended_at=now,
            expires_at=now + timedelta(days=90),
        )
        session.add_all([source, qa, interview])
        await session.commit()
        return task, qa, interview


async def test_delete_account_data_tombstones_immediately_and_worker_cleans_private_data(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    owner = await _owner(app_client, create_user, "privacy-owner@example.com")
    await _owner(app_client, create_user, "privacy-other@example.com")
    task, qa, interview = await _seed_business_data(app_client, settings, owner)
    storage = LocalPrivateStorage(settings.resume_storage_dir)
    document_key = f"{owner.id.hex}/private-notes.md"
    await storage.put(document_key, b"private document bytes")
    async with app_client.session_factory() as session:
        document = UserDocument(
            owner_user_id=owner.id,
            title="Private notes",
            original_filename="private-notes.md",
            detected_mime="text/markdown",
            size_bytes=21,
            sha256="d" * 64,
            object_key=document_key,
            state="ready",
            chunk_count=1,
            retention_expires_at=datetime.now(UTC) + timedelta(days=90),
        )
        session.add(document)
        await session.flush()
        session.add(
            UserDocumentChunk(
                document_id=document.id,
                owner_user_id=owner.id,
                chunk_index=0,
                section_path="正文 / 1",
                content="private document bytes",
                content_hash="c" * 64,
                search_text="private document bytes",
                token_count=3,
                embedding=[0.0] * 1024,
            )
        )
        await session.commit()
        document_id = document.id
    client = app_client.client
    _login(client, "privacy-owner@example.com")

    key = str(uuid.uuid4())
    accepted = client.delete("/api/v1/me/data", headers=_headers(client, key))
    assert accepted.status_code == 202, accepted.text
    request_id = accepted.json()["request_id"]
    assert accepted.json()["state"] == "requested"
    replay = client.delete("/api/v1/me/data", headers=_headers(client, key))
    assert replay.status_code == 202
    assert replay.json()["request_id"] == request_id
    assert "private-resume" not in accepted.text

    async with app_client.session_factory() as session:
        persisted_task = await session.get(ResumeTask, task.id)
        persisted_qa = await session.get(QaRequest, qa.id)
        persisted_interview = await session.get(Interview, interview.id)
        persisted_document = await session.get(UserDocument, document_id)
        source = (
            await session.execute(select(ResumeFile).where(ResumeFile.resume_task_id == task.id))
        ).scalar_one()
        assert persisted_task is not None and persisted_task.deleted_at is not None
        assert persisted_qa is not None and persisted_qa.deleted_at is not None
        assert persisted_interview is not None and persisted_interview.deleted_at is not None
        assert persisted_document is not None and persisted_document.deleted_at is not None
        assert source.storage_state == "delete_pending"

    assert client.get("/api/v1/history?type=resume").json()["items"] == []
    assert client.get("/api/v1/history?type=qa").json()["items"] == []

    outcome = await _worker(app_client, settings).run_once()
    if outcome.outcome != "succeeded":
        async with app_client.session_factory() as session:
            job = (
                await session.execute(
                    select(AsyncJob)
                    .where(AsyncJob.job_type == "delete_account_data")
                    .order_by(AsyncJob.created_at.desc())
                    .limit(1)
                )
            ).scalar_one()
        raise AssertionError(
            f"deletion worker outcome={outcome.outcome} "
            f"code={job.error_code} detail={job.error_detail}"
        )
    storage_root = LocalPrivateStorage(settings.resume_storage_dir)._root
    assert not (storage_root / f"{owner.id.hex}/private-resume.pdf").exists()
    assert not (storage_root / document_key).exists()
    async with app_client.session_factory() as session:
        request = await session.get(DataDeletionRequest, uuid.UUID(request_id))
        persisted_task = await session.get(ResumeTask, task.id)
        persisted_qa = await session.get(QaRequest, qa.id)
        persisted_interview = await session.get(Interview, interview.id)
        persisted_document = await session.get(UserDocument, document_id)
        persisted_user = await session.get(User, owner.id)
        assert request is not None and request.state == "completed"
        assert request.result is not None
        assert request.result["business_scope_deleted"] is True
        assert persisted_task is None
        assert persisted_qa is None
        assert persisted_interview is None
        assert persisted_document is None
        assert persisted_user is not None and persisted_user.status == "deleted"
        audit = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "delete_account_data")
            )
        ).scalar_one()
        assert "privacy-owner" not in audit.resource_id_hash
        assert "private" not in str(audit.__dict__)
    status = client.get(f"/api/v1/me/data-deletion/{request_id}")
    assert status.status_code == 200
    assert status.json()["state"] == "completed"
    assert client.get("/api/v1/dashboard").status_code == 401

    client.cookies.clear()
    _login(client, "privacy-other@example.com")
    assert client.get(f"/api/v1/me/data-deletion/{request_id}").status_code == 404


async def test_retention_cleanup_hides_expired_data_and_deletes_expired_audit(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    owner = await _owner(app_client, create_user, "retention-owner@example.com")
    now = datetime.now(UTC)
    async with app_client.session_factory() as session:
        expired_task = ResumeTask(
            owner_user_id=owner.id,
            state="completed",
            created_at=now - timedelta(days=100),
            completed_at=now - timedelta(days=100),
            expires_at=now - timedelta(days=1),
        )
        session.add(expired_task)
        await session.flush()
        session.add(
            ResumeFile(
                resume_task_id=expired_task.id,
                owner_user_id=owner.id,
                original_filename="expired.pdf",
                declared_mime="application/pdf",
                detected_mime="application/pdf",
                size_bytes=10,
                sha256="e" * 64,
                object_key=f"{owner.id.hex}/expired.pdf",
                retention_expires_at=now - timedelta(days=1),
            )
        )
        expired_audit = AuditEvent(
            action="login",
            resource_type="user",
            resource_id_hash="a" * 64,
            result="success",
            request_id=f"expired-{uuid.uuid4()}",
            created_at=now - timedelta(days=366),
            expires_at=now - timedelta(days=1),
        )
        session.add(expired_audit)
        await session.commit()
        expired_audit_id = expired_audit.id

    worker = _worker(app_client, settings)
    async with app_client.session_factory() as session:
        job_id = uuid.uuid4()
        from app.db.models import AsyncJob

        session.add(
            AsyncJob(
                id=job_id,
                job_type="retention_cleanup",
                resource_type="retention",
                resource_id=uuid.uuid4(),
                idempotency_key=f"retention-{uuid.uuid4()}",
                max_attempts=3,
                next_run_at=now - timedelta(seconds=1),
            )
        )
        await session.commit()
    outcome = await worker.run_once()
    assert outcome.outcome == "succeeded"
    async with app_client.session_factory() as session:
        task = await session.get(ResumeTask, expired_task.id)
        audit = await session.get(AuditEvent, expired_audit_id)
        source = (
            await session.execute(
                select(ResumeFile).where(ResumeFile.resume_task_id == expired_task.id)
            )
        ).scalar_one()
        assert task is not None and task.deleted_at is not None
        assert source.storage_state == "deleted"
        assert audit is None


async def test_ops_metrics_requires_token_and_returns_only_aggregates(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "metrics-owner@example.com")
    app_client.app.state.settings = settings.model_copy(update={"ops_metrics_token": "ops-secret"})
    client = app_client.client

    hidden = client.get("/api/v1/ops/metrics")
    assert hidden.status_code == 404
    assert "ops-secret" not in hidden.text

    visible = client.get(
        "/api/v1/ops/metrics",
        headers={"Authorization": "Bearer ops-secret"},
    )
    assert visible.status_code == 200, visible.text
    payload = visible.json()
    assert "jobs_by_state" in payload
    assert "jobs_by_type" in payload
    assert "deletion_requests_by_state" in payload
    assert "interview_scoring_failed" in payload
    assert "metrics-owner" not in visible.text
