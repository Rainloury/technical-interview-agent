"""Dashboard response models."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.auth import UserSummary


class RecentTask(BaseModel):
    """A compact, non-sensitive task summary."""

    id: UUID
    type: Literal["resume", "qa"]
    title: str
    state: str
    updated_at: datetime


class RecentInterview(BaseModel):
    """A compact interview summary."""

    id: UUID
    direction: Literal["backend", "frontend", "fullstack"]
    state: str
    updated_at: datetime


class DashboardResponse(BaseModel):
    """The account and recent activity needed by the workspace."""

    user: UserSummary
    recent_tasks: list[RecentTask]
    recent_interviews: list[RecentInterview]
    server_time: datetime
