"""不含存储定位符或内容主体的公开私有文档 DTO。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

UserDocumentState = Literal["uploaded", "processing", "ready", "failed", "deleted"]


class DocumentAccepted(BaseModel):
    """已接受的私有文档上传元数据。"""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    state: UserDocumentState
    created_at: datetime


class DocumentBatchAccepted(BaseModel):
    """一批私有文档上传的已接受元数据。"""

    model_config = ConfigDict(extra="forbid")

    documents: list[DocumentAccepted]
    original_filenames: list[str]


class DocumentItem(BaseModel):
    """所有者可见的文档状态和有界元数据。"""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    original_filename: str
    state: UserDocumentState
    chunk_count: int
    failure_code: str | None
    error_message: str | None
    index_version: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    retention_expires_at: datetime
    visibility: Literal["private", "shared"] = "private"
    can_delete: bool = True


class DocumentPage(BaseModel):
    """稳定的游标分页私有文档列表。"""

    model_config = ConfigDict(extra="forbid")

    items: list[DocumentItem]
    next_cursor: str | None
