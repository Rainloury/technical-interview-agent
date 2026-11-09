"""最小化的不可逆审计事件写入。"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent


async def audit(
    session: AsyncSession,
    *,
    action: str,
    resource_id_hash: str,
    result: str,
    request_id: str,
    resource_type: str = "user",
) -> None:
    """追加一条审计记录;request_id 必须由调用方提供,不得硬编码。"""

    session.add(
        AuditEvent(
            action=action,
            resource_type=resource_type,
            resource_id_hash=resource_id_hash,
            result=result,
            request_id=request_id[:120] or uuid.uuid4().hex,
        )
    )
