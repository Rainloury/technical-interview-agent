"""Storage adapter selection and OSS request contract tests."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from app.config import Settings
from app.storage import LocalPrivateStorage, OssPrivateStorage, create_resume_storage


def test_storage_backend_selects_local_when_explicitly_local(tmp_path: object) -> None:
    settings = Settings(
        resume_storage_backend="local",
        resume_storage_dir=str(tmp_path),
    )

    assert isinstance(create_resume_storage(settings), LocalPrivateStorage)


def test_oss_backend_requires_credentials() -> None:
    settings = Settings(
        resume_storage_backend="oss",
        oss_endpoint="https://oss-cn-hangzhou.aliyuncs.com",
        oss_bucket="interview-private",
        oss_access_key_id="",
        oss_access_key_secret="",
    )

    with pytest.raises(ValueError, match="OSS_ACCESS_KEY_ID"):
        create_resume_storage(settings)


@pytest.mark.asyncio
async def test_oss_put_get_delete_use_private_bucket_and_signature() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, content=b"resume-bytes", request=request)
        if request.method == "DELETE":
            return httpx.Response(404, request=request)
        return httpx.Response(200, request=request)

    def clock() -> datetime:
        return datetime(2026, 10, 18, 0, 0, 0, tzinfo=UTC)

    storage = OssPrivateStorage(
        endpoint="https://oss-cn-hangzhou.aliyuncs.com",
        bucket="interview-private",
        access_key_id="test-key",
        access_key_secret="test-secret",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        clock=clock,
    )

    await storage.put("owner/file.pdf", b"resume-bytes")
    assert await storage.get("owner/file.pdf") == b"resume-bytes"
    await storage.delete("owner/file.pdf")

    assert [request.method for request in requests] == ["PUT", "GET", "DELETE"]
    assert all(
        str(request.url).startswith(
            "https://interview-private.oss-cn-hangzhou.aliyuncs.com/resumes/"
        )
        for request in requests
    )
    assert all(request.headers["Authorization"].startswith("OSS test-key:") for request in requests)
    assert requests[0].headers["Content-MD5"]
