"""Public retrieval-QA DTOs with bounded evidence and stable state."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

QaState = Literal["created", "retrieving", "answering", "completed", "failed"]
EvidenceStatus = Literal["supported", "model_knowledge", "insufficient"]
AnswerPreference = Literal["concise", "detailed"]


class QaCreate(BaseModel):
    """One bounded technical question."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    answer_preference: AnswerPreference = "concise"

    @model_validator(mode="after")
    def reject_blank_question(self) -> QaCreate:
        if not self.question.strip():
            raise ValueError("question must not be blank")
        return self


class QaAccepted(BaseModel):
    """Accepted QA request metadata."""

    qa_request_id: UUID
    stream_url: str
    state: QaState


class QaEvidenceView(BaseModel):
    """Public evidence snapshot with no internal source identifiers."""

    model_config = ConfigDict(extra="forbid")

    citation_id: str
    title: str
    section_path: str
    snippet: str = Field(max_length=200)
    relevance_score: float = Field(ge=0, le=1)
    source_state: Literal["available", "source_deleted"]
    source_kind: Literal["system", "user_document", "shared_document"] = "system"


class QaAnswerView(BaseModel):
    """Validated structured answer returned to the owner."""

    model_config = ConfigDict(extra="forbid")

    direct_answer: str
    explanation: str
    evidence_ids: list[str]
    extended_questions: list[str]
    evidence_status: EvidenceStatus

    @model_validator(mode="before")
    @classmethod
    def normalize_historical_citations(cls, value: Any) -> Any:
        """Hide citations from legacy rows whose status cannot use them."""

        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if normalized.get("evidence_status") in {"model_knowledge", "insufficient"}:
            normalized["evidence_ids"] = []
        return normalized


class QaRequestView(BaseModel):
    """Owner-visible request, final answer, and public evidence."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    question: str
    answer_preference: AnswerPreference
    state: QaState
    answer: QaAnswerView | None
    evidence: list[QaEvidenceView]
    evidence_status: EvidenceStatus
    error: dict[str, Any] | None
    created_at: datetime
    completed_at: datetime | None
    last_event_seq: int
