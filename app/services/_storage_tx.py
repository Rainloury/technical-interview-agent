"""用例层与对象存储之间的显式补偿边界。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import suppress

from sqlalchemy.ext.asyncio import AsyncSession

from app.storage import ObjectStorage

UploadObjects = list[str]
Cleanup = Callable[[], Awaitable[None]]


async def cleanup_uploaded_objects(storage: ObjectStorage, object_keys: UploadObjects) -> None:
    """尽力删除已上传对象;清理失败不覆盖触发补偿的原始异常。"""

    for object_key in object_keys:
        with suppress(Exception):
            await storage.delete(object_key)


def uploaded_object_keys() -> UploadObjects:
    """返回一个由底层写入方在 put 之前追加对象键的列表。"""

    return []


async def put_object(
    storage: ObjectStorage,
    object_key: str,
    content: bytes,
    *,
    uploaded: UploadObjects,
) -> None:
    """在写入对象前登记键,保证 put 成功后的任何失败都能触发清理。"""

    uploaded.append(object_key)
    await storage.put(object_key, content)


async def rollback_with_object_cleanup(
    session: AsyncSession,
    storage: ObjectStorage,
    uploaded: UploadObjects,
) -> None:
    """回滚数据库事务并清理本次事务已写入的私有对象。"""

    await session.rollback()
    await cleanup_uploaded_objects(storage, uploaded)
