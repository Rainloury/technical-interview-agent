"""仪表盘响应模型。"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.auth import UserSummary


class RecentTask(BaseModel):
    """紧凑、非敏感的任务摘要。"""

    id: UUID
    type: Literal["resume", "qa"]
    title: str
    state: str
    updated_at: datetime


class RecentInterview(BaseModel):
    """紧凑的面试摘要。"""

    id: UUID
    direction: Literal["backend", "frontend", "fullstack"]
    state: str
    updated_at: datetime


class DashboardResponse(BaseModel):
    """工作区所需的账户和近期活动。"""

    user: UserSummary
    recent_tasks: list[RecentTask]
    recent_interviews: list[RecentInterview]
    server_time: datetime


class OperationalMetrics(BaseModel):
    """不含用户内容或资源 ID 的聚合运营计数器。"""

    generated_at: datetime
    jobs_by_state: dict[str, int]
    jobs_by_type: dict[str, int]
    interview_scoring_failed: int
    interview_termination_reasons: dict[str, int]
    deletion_requests_by_state: dict[str, int]
    expired_audit_events: int
    details: dict[str, Any] | None = None
