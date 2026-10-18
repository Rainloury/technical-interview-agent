"""Private object storage for original resume files."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import shutil
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from app.config import Settings


class ObjectStorage(Protocol):
    """Narrow storage contract used by the resume service and Worker."""

    async def put(self, object_key: str, content: bytes) -> None: ...

    async def get(self, object_key: str) -> bytes: ...

    async def delete(self, object_key: str) -> None: ...


class LocalPrivateStorage:
    """Private local adapter for development; object keys never leave the server."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser().resolve()

    def _path(self, object_key: str) -> Path:
        if not object_key or object_key.startswith(("/", "\\")) or ".." in Path(object_key).parts:
            raise ValueError("invalid object key")
        path = (self._root / object_key).resolve()
        if self._root not in path.parents:
            raise ValueError("object key escapes storage root")
        return path

    async def put(self, object_key: str, content: bytes) -> None:
        """Atomically write one private object with owner-only permissions."""

        destination = self._path(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as handle:
                os.chmod(temporary, 0o600)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    async def get(self, object_key: str) -> bytes:
        """Read a private object, raising ``FileNotFoundError`` when absent."""

        return self._path(object_key).read_bytes()

    async def delete(self, object_key: str) -> None:
        """Delete an object idempotently."""

        self._path(object_key).unlink(missing_ok=True)

    def clear_for_tests(self) -> None:
        """Remove the adapter root in isolated tests only."""

        shutil.rmtree(self._root, ignore_errors=True)


class OssPrivateStorage:
    """Private Alibaba Cloud OSS adapter using the official V1 request signature."""

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key_id: str,
        access_key_secret: str,
        prefix: str = "resumes/",
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._bucket = bucket
        self._access_key_id = access_key_id
        self._access_key_secret = access_key_secret
        self._prefix = prefix.strip("/")
        self._client = client or httpx.AsyncClient(timeout=30)
        self._clock = clock or (lambda: datetime.now(UTC))

    def _object_key(self, object_key: str) -> str:
        path = Path(object_key)
        if not object_key or object_key.startswith(("/", "\\")) or ".." in path.parts:
            raise ValueError("invalid object key")
        return f"{self._prefix}/{object_key}" if self._prefix else object_key

    def _url(self, object_key: str) -> str:
        encoded = "/".join(quote(part, safe="-_.~") for part in object_key.split("/"))
        parsed = urlsplit(self._endpoint)
        host = parsed.hostname or ""
        bucket_prefix = f"{self._bucket}."
        if not host.startswith(bucket_prefix):
            host = f"{bucket_prefix}{host}"
        netloc = host if parsed.port is None else f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, f"/{encoded}", "", ""))

    def _authorization(
        self,
        *,
        method: str,
        object_key: str,
        content_type: str,
        content_md5: str,
        date: str,
    ) -> str:
        resource = f"/{self._bucket}/{object_key}"
        canonical = "\n".join(
            [
                method,
                content_md5,
                content_type,
                date,
                resource,
            ]
        )
        digest = hmac.new(
            self._access_key_secret.encode(),
            canonical.encode(),
            hashlib.sha1,
        ).digest()
        signature = base64.b64encode(digest).decode()
        return f"OSS {self._access_key_id}:{signature}"

    async def put(self, object_key: str, content: bytes) -> None:
        key = self._object_key(object_key)
        content_md5 = base64.b64encode(
            hashlib.md5(content, usedforsecurity=False).digest()
        ).decode()
        date = format_datetime(self._clock(), usegmt=True)
        headers = {
            "Authorization": self._authorization(
                method="PUT",
                object_key=key,
                content_type="application/octet-stream",
                content_md5=content_md5,
                date=date,
            ),
            "Content-MD5": content_md5,
            "Content-Type": "application/octet-stream",
            "Date": date,
        }
        response = await self._client.put(self._url(key), content=content, headers=headers)
        response.raise_for_status()

    async def get(self, object_key: str) -> bytes:
        key = self._object_key(object_key)
        date = format_datetime(self._clock(), usegmt=True)
        headers = {
            "Authorization": self._authorization(
                method="GET",
                object_key=key,
                content_type="",
                content_md5="",
                date=date,
            ),
            "Date": date,
        }
        response = await self._client.get(self._url(key), headers=headers)
        if response.status_code == 404:
            raise FileNotFoundError(key)
        response.raise_for_status()
        return response.content

    async def delete(self, object_key: str) -> None:
        key = self._object_key(object_key)
        date = format_datetime(self._clock(), usegmt=True)
        headers = {
            "Authorization": self._authorization(
                method="DELETE",
                object_key=key,
                content_type="",
                content_md5="",
                date=date,
            ),
            "Date": date,
        }
        response = await self._client.delete(self._url(key), headers=headers)
        if response.status_code not in {204, 404}:
            response.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()


def create_resume_storage(settings: Settings) -> ObjectStorage:
    """Create the configured storage adapter."""

    if settings.resume_storage_backend == "oss":
        required = {
            "OSS_ENDPOINT": settings.oss_endpoint,
            "OSS_BUCKET": settings.oss_bucket,
            "OSS_ACCESS_KEY_ID": settings.oss_access_key_id,
            "OSS_ACCESS_KEY_SECRET": settings.oss_access_key_secret,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"missing OSS configuration: {', '.join(missing)}")
        assert settings.oss_endpoint is not None
        assert settings.oss_bucket is not None
        assert settings.oss_access_key_id is not None
        assert settings.oss_access_key_secret is not None
        return OssPrivateStorage(
            endpoint=settings.oss_endpoint,
            bucket=settings.oss_bucket,
            access_key_id=settings.oss_access_key_id.get_secret_value(),
            access_key_secret=settings.oss_access_key_secret.get_secret_value(),
            prefix=settings.oss_prefix,
        )
    return LocalPrivateStorage(settings.resume_storage_dir)
