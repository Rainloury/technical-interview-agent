"""公开简历任务 DTO,不含存储键或受保护答案材料。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

ResumeState = Literal[
    "uploaded",
    "extracting",
    "analyzing",
    "generating_questions",
    "completed",
    "failed",
    "source_deleted",
]
ResumeFailureStage = Literal["upload", "extract", "analyze", "generate"]


class ResumeAccepted(BaseModel):
    """已接受的上传元数据。"""

    resume_task_id: UUID
    state: ResumeState
    created_at: datetime


class ResumeAnalysisView(BaseModel):
    """仅公开已批准的分析部分。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    skills: Any
    projects: Any
    unverified_items: Any


class GeneratedQuestionView(BaseModel):
    """可安全向其所有者暴露的问题材料。"""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    sequence: int
    question_text: str
    category: str
    difficulty: Literal["easy", "medium", "hard"]
    assessment_points: Any
    evidence_refs: Any


class ResumeTaskView(BaseModel):
    """所有者可见的任务状态和派生输出。"""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    state: ResumeState
    failure_stage: ResumeFailureStage | None
    error_code: str | None
    analysis: ResumeAnalysisView | None
    questions: list[GeneratedQuestionView]
    created_at: datetime
    completed_at: datetime | None
