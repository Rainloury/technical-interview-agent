"""Public interview DTOs with a strict in-progress/report boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.interview_contracts import DifficultyProfile, Direction

InterviewState = Literal[
    "created",
    "in_progress",
    "completed",
    "cancelled",
    "timed_out",
    "failed",
]
TurnType = Literal["main", "follow_up"]
TurnState = Literal[
    "pending",
    "awaiting_answer",
    "scoring",
    "passed",
    "failed",
    "scoring_failed",
    "branch_completed",
    "skipped",
    "unanswered",
    "cancelled",
]
ScoringStatus = Literal["complete", "incomplete_scoring"]
ScoreBand = Literal["below_70", "70_84", "85_plus"]


class InterviewCreate(BaseModel):
    """One bounded interview configuration."""

    model_config = ConfigDict(extra="forbid")

    direction: Direction
    difficulty: DifficultyProfile = "balanced"
    topic_keys: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def reject_blank_topics(self) -> InterviewCreate:
        if any(not value.strip() for value in self.topic_keys):
            raise ValueError("topic keys must not be blank")
        return self


class InterviewConfigurationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: Direction
    difficulty: DifficultyProfile
    topic_keys: list[str]


class InterviewCreated(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interview_id: UUID
    state: InterviewState
    main_question_count: int
    deadline_at: datetime | None
    configuration: InterviewConfigurationView


class InterviewTurnView(BaseModel):
    """Only the question and neutral process metadata are public in-progress."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    type: TurnType
    depth: int = Field(ge=0, le=2)
    question_text: str
    topic_key: str
    difficulty: Literal["easy", "medium", "hard"]
    state: TurnState


class InterviewProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_questions_completed: int = Field(ge=0)
    main_questions_total: int = Field(ge=0)
    main_questions_remaining: int = Field(ge=0)
    current_follow_up_chain: (
        Literal[
            "awaiting_answer",
            "scoring",
            "generating_follow_up",
            "completed",
        ]
        | None
    ) = None
    remaining_seconds: int = Field(ge=0)


class InterviewStartView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interview_id: UUID
    state: InterviewState
    server_time: datetime
    deadline_at: datetime | None
    current_turn: InterviewTurnView | None
    progress: InterviewProgress


class InterviewView(BaseModel):
    """Owner-visible live view that cannot carry protected feedback fields."""

    model_config = ConfigDict(extra="forbid")

    interview_id: UUID
    state: InterviewState
    direction: Direction
    configuration: InterviewConfigurationView
    server_time: datetime
    deadline_at: datetime | None
    ended_at: datetime | None
    current_turn: InterviewTurnView | None
    submitted_turns: list[InterviewTurnView]
    progress: InterviewProgress


class InterviewTurnAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: UUID
    state: Literal["scoring"]
    accepted_at: datetime
    progress: InterviewProgress
    next_action: Literal["wait"]


class InterviewBranchAction(BaseModel):
    """Neutral action acknowledgement with no score or branch-trigger reason."""

    model_config = ConfigDict(extra="forbid")

    interview_id: UUID
    turn_id: UUID
    state: InterviewState
    progress: InterviewProgress
    next_action: Literal["wait"]


class InterviewReportTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    parent_turn_id: UUID | None
    type: TurnType
    depth: int = Field(ge=0, le=2)
    question_text: str
    topic_key: str
    difficulty: Literal["easy", "medium", "hard"]
    result: TurnState
    score_total: float | None
    score_band: ScoreBand | None
    score_breakdown: dict[str, Any] | None
    loss_reasons: list[str]
    reference_answer: str | None
    submitted_at: datetime | None


class WrongQuestionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    turn_id: UUID
    parent_turn_id: UUID | None
    question_text: str
    topic_key: str
    difficulty: Literal["easy", "medium", "hard"]
    score_breakdown: dict[str, Any]
    loss_reasons: list[str]
    created_at: datetime


class WeakPointEvidenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wrong_question_id: UUID
    turn_id: UUID
    loss_reason_hash: str


class WeakPointSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    topic_key: str
    title: str
    severity: float
    failure_count: int
    last_failure_at: datetime
    review_advice: dict[str, Any]
    state: str
    evidence: list[WeakPointEvidenceView]


class InterviewReportView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interview_id: UUID
    state: InterviewState
    direction: Direction
    scoring_status: ScoringStatus
    server_time: datetime
    summary: dict[str, Any]
    turns: list[InterviewReportTurn]
    wrong_questions: list[WrongQuestionSummary]
    weak_points: list[WeakPointSummary]


class WrongQuestionDetail(WrongQuestionSummary):
    interview_id: UUID
    answer_text: str
    reference_answer: str
    state: str
    expires_at: datetime


class WrongQuestionPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[WrongQuestionDetail]
    next_cursor: str | None


class WeakPointDetail(WeakPointSummary):
    pass


class WeakPointPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[WeakPointDetail]
    next_cursor: str | None
