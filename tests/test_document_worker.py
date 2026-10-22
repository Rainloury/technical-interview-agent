"""Private document Worker indexing, retry, deletion, and isolation tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.config import Settings
from app.db.models import AsyncJob, UserDocument, UserDocumentChunk
from app.prompts.loader import PromptLoader
from app.rag.ollama import OllamaEmbeddingError
from app.storage import LocalPrivateStorage
from app.worker import ResumeWorker
from sqlalchemy import select

from tests.conftest import AppHarness
from tests.test_account_api import _login, _write_headers

pytestmark = pytest.mark.integration


class FakeEmbedding:
    def __init__(self, *, failures: int = 0) -> None:
        self.failures = failures
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls <= self.failures:
            raise OllamaEmbeddingError("embedding_unavailable", retryable=True)
        return [[0.1] * 1024 for _ in texts]


def _worker(
    app_client: AppHarness,
    settings: Settings,
    embedding: FakeEmbedding | None = None,
    *,
    worker_id: str | None = None,
) -> ResumeWorker:
    return ResumeWorker(
        settings=settings.model_copy(update={"worker_lease_seconds": 60}),
        session_factory=app_client.session_factory,
        storage=LocalPrivateStorage(settings.resume_storage_dir),
        llm=object(),  # type: ignore[arg-type]
        prompt_loader=PromptLoader("app/prompts"),
        embedding_client=embedding or FakeEmbedding(),
        worker_id=worker_id or f"document-worker-{uuid.uuid4().hex[:8]}",
    )


async def _upload_document(
    app_client: AppHarness,
    create_user: Any,
    *,
    email: str = "doc-worker@example.com",
    filename: str = "notes.md",
    content: bytes = b"# Redis\n\nRedis uses LRU eviction and retries.",
) -> uuid.UUID:
    async with app_client.session_factory() as session:
        session.add(create_user(email))
        await session.commit()
    client = app_client.client
    _login(client, email)
    response = client.post(
        "/api/v1/documents",
        files={"file": (filename, content, "text/markdown")},
        data={"title": "Worker notes"},
        headers={**_write_headers(client), "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 202, response.text
    return uuid.UUID(response.json()["document_id"])


async def test_worker_indexes_document_and_is_idempotent(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    document_id = await _upload_document(app_client, create_user)
    worker = _worker(app_client, settings)

    first = await worker.run_once()
    assert first.outcome == "succeeded"
    async with app_client.session_factory() as session:
        document = await session.get(UserDocument, document_id)
        chunks = list(
            (
                await session.execute(
                    select(UserDocumentChunk).where(UserDocumentChunk.document_id == document_id)
                )
            ).scalars()
        )
        assert document is not None
        assert document.state == "ready"
        assert document.chunk_count == len(chunks)
        assert document.completed_at is not None
        assert chunks
        assert len(chunks[0].embedding) == 1024


async def test_document_worker_retries_embedding_then_succeeds(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    document_id = await _upload_document(
        app_client,
        create_user,
        email="doc-retry-worker@example.com",
    )
    embedding = FakeEmbedding(failures=1)
    first = await _worker(app_client, settings, embedding).run_once()
    assert first.outcome == "retry_scheduled"
    async with app_client.session_factory() as session:
        job = (
            await session.execute(select(AsyncJob).where(AsyncJob.resource_id == document_id))
        ).scalar_one()
        job.next_run_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    second = await _worker(
        app_client,
        settings,
        embedding,
        worker_id="document-retry-worker-2",
    ).run_once()
    assert second.outcome == "succeeded"


async def test_document_worker_fails_without_partial_chunks(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    document_id = await _upload_document(
        app_client,
        create_user,
        email="doc-fail-worker@example.com",
    )
    async with app_client.session_factory() as session:
        job = (
            await session.execute(select(AsyncJob).where(AsyncJob.resource_id == document_id))
        ).scalar_one()
        job.max_attempts = 1
        await session.commit()

    result = await _worker(
        app_client,
        settings,
        FakeEmbedding(failures=10),
    ).run_once()
    assert result.outcome == "dead_letter"
    async with app_client.session_factory() as session:
        document = await session.get(UserDocument, document_id)
        chunks = list(
            (
                await session.execute(
                    select(UserDocumentChunk).where(UserDocumentChunk.document_id == document_id)
                )
            ).scalars()
        )
        assert document is not None
        assert document.state == "failed"
        assert chunks == []


async def test_document_delete_removes_object_and_chunks(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    document_id = await _upload_document(
        app_client,
        create_user,
        email="doc-delete-worker@example.com",
    )
    first = await _worker(app_client, settings).run_once()
    assert first.outcome == "succeeded"
    async with app_client.session_factory() as session:
        document = await session.get(UserDocument, document_id)
        assert document is not None
        object_key = document.object_key
    storage = LocalPrivateStorage(settings.resume_storage_dir)
    content = await storage.get(object_key)
    assert content

    client = app_client.client
    deleted = client.delete(
        f"/api/v1/documents/{document_id}",
        headers={**_write_headers(client), "Idempotency-Key": str(uuid.uuid4())},
    )
    assert deleted.status_code == 204
    async with app_client.session_factory() as session:
        job = (
            await session.execute(
                select(AsyncJob).where(
                    AsyncJob.resource_id == document_id,
                    AsyncJob.job_type == "delete_document",
                )
            )
        ).scalar_one()
        job.next_run_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    result = await _worker(
        app_client,
        settings,
        worker_id="document-delete-worker",
    ).run_once()
    assert result.outcome == "succeeded"
    async with app_client.session_factory() as session:
        chunks = list(
            (
                await session.execute(
                    select(UserDocumentChunk).where(UserDocumentChunk.document_id == document_id)
                )
            ).scalars()
        )
        document = await session.get(UserDocument, document_id)
        assert chunks == []
        assert document is not None and document.deletion_state == "deleted"


async def test_stale_document_worker_cannot_revive_deleted_document(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    document_id = await _upload_document(
        app_client,
        create_user,
        email="doc-stale-worker@example.com",
    )
    async with app_client.session_factory() as session:
        document = await session.get(UserDocument, document_id)
        assert document is not None
        document.state = "deleted"
        document.deletion_state = "pending"
        document.deleted_at = datetime.now(UTC)
        job = (
            await session.execute(select(AsyncJob).where(AsyncJob.resource_id == document_id))
        ).scalar_one()
        job.next_run_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    result = await _worker(app_client, settings).run_once()
    assert result.outcome == "succeeded"
    async with app_client.session_factory() as session:
        document = await session.get(UserDocument, document_id)
        chunks = list(
            (
                await session.execute(
                    select(UserDocumentChunk).where(UserDocumentChunk.document_id == document_id)
                )
            ).scalars()
        )
        assert document is not None
        assert document.state == "deleted"
        assert chunks == []


async def test_document_retention_expiry_hides_document(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    document_id = await _upload_document(
        app_client,
        create_user,
        email="doc-retention@example.com",
    )
    await _worker(app_client, settings).run_once()
    client = app_client.client
    async with app_client.session_factory() as session:
        document = await session.get(UserDocument, document_id)
        assert document is not None
        document.retention_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    listing = client.get("/api/v1/documents")
    assert listing.status_code == 200
    assert all(item["id"] != str(document_id) for item in listing.json()["items"])
