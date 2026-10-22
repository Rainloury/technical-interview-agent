"""Public private-document DTOs with no storage locators or content bodies."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

UserDocumentState = Literal["uploaded", "processing", "ready", "failed", "deleted"]


class DocumentAccepted(BaseModel):
    """Accepted private-document upload metadata."""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    state: UserDocumentState
    created_at: datetime


class DocumentBatchAccepted(BaseModel):
    """Accepted metadata for one batch of private-document uploads."""

    model_config = ConfigDict(extra="forbid")

    documents: list[DocumentAccepted]
    original_filenames: list[str]


class DocumentItem(BaseModel):
    """Owner-visible document status and bounded metadata."""

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


class DocumentPage(BaseModel):
    """Stable cursor-paginated private document list."""

    model_config = ConfigDict(extra="forbid")

    items: list[DocumentItem]
    next_cursor: str | None
