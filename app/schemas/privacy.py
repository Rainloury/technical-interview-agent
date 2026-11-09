"""公开的隐私请求和删除状态 DTO。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

DeletionState = Literal["requested", "deleting", "completed", "failed"]


class DataDeletionAccepted(BaseModel):
    """在异步清理完成前返回的中性接受。"""

    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    state: Literal["requested"]
    accepted_at: datetime


class DataDeletionStatus(BaseModel):
    """最小删除状态,不含资源 ID 或用户内容。"""

    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    state: DeletionState
    scope: list[str]
    result: dict[str, Any] | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
