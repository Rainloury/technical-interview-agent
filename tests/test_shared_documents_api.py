"""Administrator-only shared document upload and all-user read access."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.db.models import AsyncJob, SharedDocument
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import AppHarness
from tests.test_account_api import _login, _write_headers

pytestmark = pytest.mark.integration


def _upload(
    client: TestClient,
    content: bytes = b"# Shared retry\n\nUse bounded retries.",
    *,
    filename: str = "shared.md",
    mime: str = "text/markdown",
    key: str | None = None,
) -> Any:
    return client.post(
        "/api/v1/shared-documents",
        files={"file": (filename, content, mime)},
        data={"title": "共享重试手册"},
        headers={**_write_headers(client), "Idempotency-Key": key or str(uuid.uuid4())},
    )


async def test_anonymous_cannot_access_shared_document_read_or_write(
    app_client: AppHarness,
) -> None:
    client = app_client.client
    assert client.get("/api/v1/shared-documents").status_code == 401
    assert _upload(client).status_code == 401


async def test_regular_user_cannot_upload_shared_document(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    async with app_client.session_factory() as session:
        session.add(create_user("shared-regular@example.com"))
        await session.commit()

    client = app_client.client
    _login(client, "shared-regular@example.com")
    response = _upload(client)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "admin_required"
    async with app_client.session_factory() as session:
        assert (await session.execute(select(SharedDocument))).scalars().all() == []
        assert (
            await session.execute(
                select(AsyncJob).where(AsyncJob.resource_type == "shared_document")
            )
        ).scalars().all() == []


async def test_admin_can_upload_shared_document_and_job_is_resource_scoped(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    async with app_client.session_factory() as session:
        session.add(create_user("shared-admin@example.com", role="admin"))
        await session.commit()

    client = app_client.client
    _login(client, "shared-admin@example.com")
    response = _upload(client, key="shared-upload-key")

    assert response.status_code == 202, response.text
    document_id = uuid.UUID(response.json()["document_id"])
    async with app_client.session_factory() as session:
        document = await session.get(SharedDocument, document_id)
        job = (
            await session.execute(select(AsyncJob).where(AsyncJob.resource_id == document_id))
        ).scalar_one()
    assert document is not None
    assert document.state == "uploaded"
    assert job.resource_type == "shared_document"


async def test_all_authenticated_users_can_list_and_read_shared_document(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    async with app_client.session_factory() as session:
        session.add_all(
            [
                create_user("shared-owner-admin@example.com", role="admin"),
                create_user("shared-reader@example.com"),
            ]
        )
        await session.commit()

    client = app_client.client
    _login(client, "shared-owner-admin@example.com")
    created = _upload(client)
    assert created.status_code == 202
    document_id = created.json()["document_id"]

    client.cookies.clear()
    _login(client, "shared-reader@example.com")
    listing = client.get("/api/v1/shared-documents")
    detail = client.get(f"/api/v1/shared-documents/{document_id}")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["visibility"] == "shared"
    assert listing.json()["items"][0]["can_delete"] is False
    assert detail.status_code == 200
    assert detail.json()["visibility"] == "shared"
    assert "object_key" not in detail.text


async def test_regular_user_cannot_delete_shared_document(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    async with app_client.session_factory() as session:
        session.add_all(
            [
                create_user("shared-delete-admin@example.com", role="admin"),
                create_user("shared-delete-regular@example.com"),
            ]
        )
        await session.commit()

    client = app_client.client
    _login(client, "shared-delete-admin@example.com")
    document_id = _upload(client).json()["document_id"]
    client.cookies.clear()
    _login(client, "shared-delete-regular@example.com")
    response = client.delete(
        f"/api/v1/shared-documents/{document_id}",
        headers={**_write_headers(client), "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "admin_required"


async def test_admin_delete_hides_document(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    async with app_client.session_factory() as session:
        session.add(create_user("shared-delete-owner@example.com", role="admin"))
        await session.commit()

    client = app_client.client
    _login(client, "shared-delete-owner@example.com")
    document_id = _upload(client).json()["document_id"]
    response = client.delete(
        f"/api/v1/shared-documents/{document_id}",
        headers={**_write_headers(client), "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 204
    assert client.get(f"/api/v1/shared-documents/{document_id}").status_code == 404
    assert client.get("/api/v1/shared-documents").json()["items"] == []


async def test_shared_batch_rolls_back_all_objects_and_jobs_on_invalid_file(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    async with app_client.session_factory() as session:
        session.add(create_user("shared-batch-admin@example.com", role="admin"))
        await session.commit()

    client = app_client.client
    _login(client, "shared-batch-admin@example.com")
    response = client.post(
        "/api/v1/shared-documents/batch",
        files=[
            ("files", ("valid.md", b"# Valid", "text/markdown")),
            ("files", ("invalid.exe", b"invalid", "application/octet-stream")),
        ],
        headers={**_write_headers(client), "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 422
    async with app_client.session_factory() as session:
        assert (await session.execute(select(SharedDocument))).scalars().all() == []
