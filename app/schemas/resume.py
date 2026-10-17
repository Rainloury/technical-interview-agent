"""Public resume task DTOs with no storage keys or protected answer material."""

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
    """Accepted upload metadata."""

    resume_task_id: UUID
    state: ResumeState
    created_at: datetime


class ResumeAnalysisView(BaseModel):
    """Only approved analysis sections are exposed."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    skills: Any
    projects: Any
    unverified_items: Any


class GeneratedQuestionView(BaseModel):
    """Question material safe to expose to its owner."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    sequence: int
    question_text: str
    category: str
    difficulty: Literal["easy", "medium", "hard"]
    assessment_points: Any
    evidence_refs: Any


class ResumeTaskView(BaseModel):
    """Owner-visible task state and derived output."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    state: ResumeState
    failure_stage: ResumeFailureStage | None
    error_code: str | None
    analysis: ResumeAnalysisView | None
    questions: list[GeneratedQuestionView]
    created_at: datetime
    completed_at: datetime | None
