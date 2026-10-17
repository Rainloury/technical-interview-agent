"""History pagination response models."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

HistoryType = Literal["resume", "qa", "interview", "wrong_question"]


class HistoryItem(BaseModel):
    """One owner-scoped history record."""

    id: UUID
    type: HistoryType
    title: str
    state: str
    updated_at: datetime


class HistoryPage(BaseModel):
    """Stable cursor page used by both web and future clients."""

    items: list[HistoryItem]
    next_cursor: str | None
