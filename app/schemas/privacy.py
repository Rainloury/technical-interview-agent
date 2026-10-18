"""Public privacy request and deletion-status DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

DeletionState = Literal["requested", "deleting", "completed", "failed"]


class DataDeletionAccepted(BaseModel):
    """Neutral acceptance returned before asynchronous cleanup completes."""

    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    state: Literal["requested"]
    accepted_at: datetime


class DataDeletionStatus(BaseModel):
    """Minimal deletion status without resource IDs or user content."""

    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    state: DeletionState
    scope: list[str]
    result: dict[str, Any] | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
