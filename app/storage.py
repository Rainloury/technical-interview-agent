"""Private object storage for original resume files."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Protocol

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


def create_resume_storage(settings: Settings) -> ObjectStorage:
    """Create the configured storage adapter."""

    return LocalPrivateStorage(settings.resume_storage_dir)
