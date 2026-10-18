"""Dashboard response models."""

from datetime import datetime
from typing import Any, Literal
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


class OperationalMetrics(BaseModel):
    """Aggregate operational counters without user content or resource IDs."""

    generated_at: datetime
    jobs_by_state: dict[str, int]
    jobs_by_type: dict[str, int]
    interview_scoring_failed: int
    interview_termination_reasons: dict[str, int]
    deletion_requests_by_state: dict[str, int]
    expired_audit_events: int
    details: dict[str, Any] | None = None
