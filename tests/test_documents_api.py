"""Owner-scoped private document upload and lifecycle API tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from app.db.models import AsyncJob, UserDocument
from app.services.documents import DocumentUpload, upload_document
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import AppHarness
from tests.test_account_api import _login, _write_headers

pytestmark = pytest.mark.integration


def _upload(
    client: TestClient,
    content: bytes,
    *,
    filename: str = "notes.md",
    mime: str = "text/markdown",
    key: str | None = None,
) -> Any:
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, content, mime)},
        data={"title": "内部资料"},
        headers={**_write_headers(client), "Idempotency-Key": key or str(uuid.uuid4())},
    )


def _upload_many(
    client: TestClient,
    files: list[tuple[str, bytes, str]],
    *,
    key: str | None = None,
) -> Any:
    return client.post(
        "/api/v1/documents/batch",
        files=[("files", item) for item in files],
        headers={**_write_headers(client), "Idempotency-Key": key or str(uuid.uuid4())},
    )


async def _owner(app_client: AppHarness, create_user: Any, email: str) -> None:
    async with app_client.session_factory() as session:
        session.add(create_user(email))
        await session.commit()


async def test_document_upload_is_owner_scoped_and_idempotent(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "doc-owner@example.com")
    await _owner(app_client, create_user, "doc-stranger@example.com")
    client = app_client.client
    _login(client, "doc-owner@example.com")
    content = b"# Redis\n\nRedis uses LRU eviction.\n"
    key = str(uuid.uuid4())

    accepted = _upload(client, content, key=key)
    assert accepted.status_code == 202, accepted.text
    document_id = accepted.json()["document_id"]
    assert accepted.json()["state"] == "uploaded"

    replay = _upload(client, content, key=key)
    assert replay.status_code == 202
    assert replay.json()["document_id"] == document_id

    detail = client.get(f"/api/v1/documents/{document_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "内部资料"
    assert detail.json()["visibility"] == "private"
    assert detail.json()["can_delete"] is True
    assert "object_key" not in detail.text

    client.cookies.clear()
    _login(client, "doc-stranger@example.com")
    assert client.get(f"/api/v1/documents/{document_id}").status_code == 404
    assert (
        client.delete(
            f"/api/v1/documents/{document_id}",
            headers={**_write_headers(client), "Idempotency-Key": str(uuid.uuid4())},
        ).status_code
        == 404
    )


async def test_batch_document_upload_creates_one_document_and_job_per_file(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "doc-batch@example.com")
    client = app_client.client
    _login(client, "doc-batch@example.com")

    response = _upload_many(
        client,
        [
            ("redis.md", b"# Redis\n\nPrivate Redis notes.", "text/markdown"),
            ("retry.txt", b"Private retry notes.", "text/plain"),
        ],
    )

    assert response.status_code == 202, response.text
    payload = response.json()
    assert len(payload["documents"]) == 2
    assert set(payload["original_filenames"]) == {
        "redis.md",
        "retry.txt",
    }
    assert all(item["state"] == "uploaded" for item in payload["documents"])
    async with app_client.session_factory() as session:
        document_ids = [uuid.UUID(item["document_id"]) for item in payload["documents"]]
        documents = list(
            (
                await session.execute(select(UserDocument).where(UserDocument.id.in_(document_ids)))
            ).scalars()
        )
        assert len(documents) == 2
        owner_id = (
            await session.execute(
                select(UserDocument.owner_user_id).where(UserDocument.id == document_ids[0])
            )
        ).scalar_one()
        jobs = list(
            (
                await session.execute(
                    select(AsyncJob).where(
                        AsyncJob.owner_user_id == owner_id,
                        AsyncJob.job_type == "process_document",
                    )
                )
            ).scalars()
        )
    assert len(jobs) == 2
    assert len({document.original_filename for document in documents}) == 2


async def test_batch_document_upload_rolls_back_when_any_file_is_invalid(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "doc-batch-invalid@example.com")
    client = app_client.client
    _login(client, "doc-batch-invalid@example.com")

    response = _upload_many(
        client,
        [
            ("valid.md", b"# Valid\n\nPrivate notes.", "text/markdown"),
            ("invalid.exe", b"not supported", "application/octet-stream"),
        ],
    )

    assert response.status_code == 422
    async with app_client.session_factory() as session:
        documents = list((await session.execute(select(UserDocument))).scalars())
        jobs = list(
            (
                await session.execute(
                    select(AsyncJob).where(AsyncJob.job_type == "process_document")
                )
            ).scalars()
        )
    assert documents == []
    assert jobs == []


async def test_batch_document_upload_rejects_duplicate_files(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "doc-batch-duplicate@example.com")
    client = app_client.client
    _login(client, "doc-batch-duplicate@example.com")

    response = _upload_many(
        client,
        [
            ("same.md", b"# Same\n\nDuplicate bytes.", "text/markdown"),
            ("same.md", b"# Same\n\nDuplicate bytes.", "text/markdown"),
        ],
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    async with app_client.session_factory() as session:
        documents = list((await session.execute(select(UserDocument))).scalars())
    assert documents == []


async def test_document_same_name_with_different_bytes_creates_distinct_records(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "doc-same-name@example.com")
    client = app_client.client
    _login(client, "doc-same-name@example.com")

    first = _upload(client, b"Redis notes one", filename="notes.md")
    second = _upload(client, b"Redis notes two", filename="notes.md")

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["document_id"] != second.json()["document_id"]


async def test_document_failed_reupload_reuses_record_and_requeues(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "doc-retry@example.com")
    client = app_client.client
    _login(client, "doc-retry@example.com")
    content = b"# Retry\n\nRetryable document."
    accepted = _upload(client, content)
    assert accepted.status_code == 202
    document_id = uuid.UUID(accepted.json()["document_id"])

    async with app_client.session_factory() as session:
        document = await session.get(UserDocument, document_id)
        assert document is not None
        document.state = "failed"
        document.failure_code = "embedding_unavailable"
        document.error_message = "索引失败"
        document.completed_at = datetime.now(UTC)
        job = (
            await session.execute(select(AsyncJob).where(AsyncJob.resource_id == document_id))
        ).scalar_one()
        job.state = "dead_letter"
        await session.commit()

    reuploaded = _upload(client, content, key=str(uuid.uuid4()))
    assert reuploaded.status_code == 202
    assert reuploaded.json()["document_id"] == str(document_id)

    async with app_client.session_factory() as session:
        documents = list(
            (
                await session.execute(
                    select(UserDocument).where(UserDocument.owner_user_id == document.owner_user_id)
                )
            ).scalars()
        )
        jobs = list(
            (
                await session.execute(select(AsyncJob).where(AsyncJob.resource_id == document_id))
            ).scalars()
        )
        assert len(documents) == 1
        assert documents[0].state == "uploaded"
        assert documents[0].failure_code is None
        assert len(jobs) >= 1


async def test_document_ready_reupload_reuses_record_without_new_job(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "doc-ready-reuse@example.com")
    client = app_client.client
    _login(client, "doc-ready-reuse@example.com")
    content = b"# Ready\n\nAlready indexed."
    accepted = _upload(client, content)
    document_id = uuid.UUID(accepted.json()["document_id"])

    async with app_client.session_factory() as session:
        document = await session.get(UserDocument, document_id)
        assert document is not None
        document.state = "ready"
        document.chunk_count = 1
        job = (
            await session.execute(select(AsyncJob).where(AsyncJob.resource_id == document_id))
        ).scalar_one()
        job.state = "succeeded"
        await session.commit()

    replay = _upload(client, content, key=str(uuid.uuid4()))
    assert replay.status_code == 202
    assert replay.json()["document_id"] == str(document_id)
    async with app_client.session_factory() as session:
        jobs = list(
            (
                await session.execute(select(AsyncJob).where(AsyncJob.resource_id == document_id))
            ).scalars()
        )
        assert len(jobs) == 1
        assert jobs[0].state == "succeeded"


async def test_document_upload_rolls_back_record_when_storage_put_fails(
    app_client: AppHarness,
    settings: Any,
    create_user: Any,
) -> None:
    owner = create_user("doc-storage-fail@example.com")
    async with app_client.session_factory() as session:
        session.add(owner)
        await session.commit()

    class FailingStorage:
        async def put(self, _key: str, _content: bytes) -> None:
            raise OSError("storage unavailable")

        async def get(self, _key: str) -> bytes:
            raise AssertionError("get should not be called")

        async def delete(self, _key: str) -> None:
            return None

    async with app_client.session_factory() as session:
        with pytest.raises(OSError):
            await upload_document(
                session,
                FailingStorage(),
                owner,
                DocumentUpload(
                    filename="notes.md",
                    declared_mime="text/markdown",
                    content=b"# notes\n\nprivate",
                ),
                idempotency_key="storage-failure-key",
                settings=settings,
            )

    async with app_client.session_factory() as session:
        documents = list(
            (
                await session.execute(
                    select(UserDocument).where(UserDocument.owner_user_id == owner.id)
                )
            ).scalars()
        )
        assert documents == []


async def test_document_upload_cleans_object_when_commit_fails(
    app_client: AppHarness,
    settings: Any,
    create_user: Any,
) -> None:
    owner = create_user("doc-commit-fail@example.com")
    async with app_client.session_factory() as session:
        session.add(owner)
        await session.commit()

    class TrackingStorage:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def put(self, _key: str, _content: bytes) -> None:
            return None

        async def get(self, _key: str) -> bytes:
            raise AssertionError("get should not be called")

        async def delete(self, key: str) -> None:
            self.deleted.append(key)

    storage = TrackingStorage()

    class FailingCommitSession(AsyncSession):
        async def commit(self) -> None:
            await super().commit()
            raise RuntimeError("commit failed")

    async with FailingCommitSession(bind=app_client.write_engine) as failing_session:
        with pytest.raises(RuntimeError, match="commit failed"):
            await upload_document(
                failing_session,
                storage,
                owner,
                DocumentUpload(
                    filename="notes.md",
                    declared_mime="text/markdown",
                    content=b"# notes\n\nprivate",
                ),
                idempotency_key="commit-failure-key",
                settings=settings,
            )

    assert storage.deleted


@pytest.mark.parametrize(
    ("filename", "content", "mime", "status", "code"),
    [
        ("notes.exe", b"binary", "application/octet-stream", 422, "unsupported_source"),
        ("notes.txt", b"", "text/plain", 422, "invalid_request"),
    ],
)
async def test_document_upload_rejects_invalid_files(
    app_client: AppHarness,
    create_user: Any,
    filename: str,
    content: bytes,
    mime: str,
    status: int,
    code: str,
) -> None:
    await _owner(app_client, create_user, "doc-invalid@example.com")
    client = app_client.client
    _login(client, "doc-invalid@example.com")

    response = _upload(client, content, filename=filename, mime=mime)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


async def test_document_upload_rejects_missing_security_headers(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "doc-security@example.com")
    client = app_client.client
    _login(client, "doc-security@example.com")

    missing_key = client.post(
        "/api/v1/documents",
        files={"file": ("notes.md", b"Redis", "text/markdown")},
        headers={**_write_headers(client)},
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["error"]["code"] == "idempotency_key_required"

    missing_csrf = client.post(
        "/api/v1/documents",
        files={"file": ("notes.md", b"Redis", "text/markdown")},
        headers={"Origin": "https://testserver", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert missing_csrf.status_code == 403


async def test_document_upload_rejects_oversized_body(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "doc-large@example.com")
    client = app_client.client
    _login(client, "doc-large@example.com")

    response = _upload(
        client, b"x" * (10 * 1024 * 1024 + 1), filename="large.txt", mime="text/plain"
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


async def test_document_delete_hides_immediately_and_is_idempotent(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "doc-delete@example.com")
    client = app_client.client
    _login(client, "doc-delete@example.com")
    accepted = _upload(client, b"# Delete\n\nPrivate content.")
    document_id = accepted.json()["document_id"]

    first = client.delete(
        f"/api/v1/documents/{document_id}",
        headers={**_write_headers(client), "Idempotency-Key": str(uuid.uuid4())},
    )
    assert first.status_code == 204
    assert client.get(f"/api/v1/documents/{document_id}").status_code == 404
    listing = client.get("/api/v1/documents")
    assert listing.status_code == 200
    assert all(item["id"] != document_id for item in listing.json()["items"])

    second = client.delete(
        f"/api/v1/documents/{document_id}",
        headers={**_write_headers(client), "Idempotency-Key": str(uuid.uuid4())},
    )
    assert second.status_code == 204

    async with app_client.session_factory() as session:
        document = await session.get(UserDocument, uuid.UUID(document_id))
        assert document is not None
        assert document.state == "deleted"
        assert document.deleted_at is not None


async def test_document_delete_idempotency_key_cannot_target_another_document(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "doc-delete-conflict@example.com")
    client = app_client.client
    _login(client, "doc-delete-conflict@example.com")
    first = _upload(client, b"# First delete\n\none")
    second = _upload(client, b"# Second delete\n\ntwo")
    first_id = first.json()["document_id"]
    second_id = second.json()["document_id"]
    key = str(uuid.uuid4())

    first_delete = client.delete(
        f"/api/v1/documents/{first_id}",
        headers={**_write_headers(client), "Idempotency-Key": key},
    )
    assert first_delete.status_code == 204
    conflict = client.delete(
        f"/api/v1/documents/{second_id}",
        headers={**_write_headers(client), "Idempotency-Key": key},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"


async def test_document_list_is_owner_scoped(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "doc-list-owner@example.com")
    await _owner(app_client, create_user, "doc-list-stranger@example.com")
    client = app_client.client
    _login(client, "doc-list-owner@example.com")
    accepted = _upload(client, b"# List\n\nPrivate list content.")
    document_id = accepted.json()["document_id"]

    listing = client.get("/api/v1/documents")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["items"]] == [document_id]

    client.cookies.clear()
    _login(client, "doc-list-stranger@example.com")
    stranger_listing = client.get("/api/v1/documents")
    assert stranger_listing.status_code == 200
    assert stranger_listing.json()["items"] == []


async def test_document_idempotency_conflict_and_list_cursor(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "doc-cursor@example.com")
    client = app_client.client
    _login(client, "doc-cursor@example.com")
    key = str(uuid.uuid4())
    first = _upload(client, b"# First\n\nCursor one.", key=key)
    assert first.status_code == 202
    conflict = _upload(client, b"# Different\n\nCursor conflict.", key=key)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"

    for index in range(2):
        response = _upload(client, f"# Cursor\n\nDocument {index}.".encode())
        assert response.status_code == 202

    page_one = client.get("/api/v1/documents", params={"limit": 2})
    assert page_one.status_code == 200
    assert len(page_one.json()["items"]) == 2
    cursor = page_one.json()["next_cursor"]
    assert cursor
    page_two = client.get("/api/v1/documents", params={"limit": 2, "cursor": cursor})
    assert page_two.status_code == 200
    assert set(item["id"] for item in page_two.json()["items"]).isdisjoint(
        item["id"] for item in page_one.json()["items"]
    )

    invalid = client.get("/api/v1/documents", params={"cursor": "not-a-cursor"})
    assert invalid.status_code == 400
