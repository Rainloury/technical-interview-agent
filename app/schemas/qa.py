"""公开的检索问答 DTO,具有受限证据和稳定状态。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

QaState = Literal["created", "retrieving", "answering", "completed", "failed"]
EvidenceStatus = Literal["supported", "model_knowledge", "insufficient"]
AnswerPreference = Literal["concise", "detailed"]


class QaCreate(BaseModel):
    """一个受边界约束的技术问题。"""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    answer_preference: AnswerPreference = "concise"

    @model_validator(mode="after")
    def reject_blank_question(self) -> QaCreate:
        if not self.question.strip():
            raise ValueError("question must not be blank")
        return self


class QaAccepted(BaseModel):
    """已接受的 QA 请求元数据。"""

    qa_request_id: UUID
    stream_url: str
    state: QaState


class QaEvidenceView(BaseModel):
    """公开证据快照,不含内部来源标识符。"""

    model_config = ConfigDict(extra="forbid")

    citation_id: str
    title: str
    section_path: str
    snippet: str = Field(max_length=200)
    relevance_score: float = Field(ge=0, le=1)
    source_state: Literal["available", "source_deleted"]
    source_kind: Literal["system", "user_document", "shared_document"] = "system"


class QaAnswerView(BaseModel):
    """返回给所有者的已校验结构化答案。"""

    model_config = ConfigDict(extra="forbid")

    direct_answer: str
    explanation: str
    evidence_ids: list[str]
    extended_questions: list[str]
    evidence_status: EvidenceStatus

    @model_validator(mode="before")
    @classmethod
    def normalize_historical_citations(cls, value: Any) -> Any:
        """对状态无法使用引用的遗留行隐藏引用。"""

        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if normalized.get("evidence_status") in {"model_knowledge", "insufficient"}:
            normalized["evidence_ids"] = []
        return normalized


class QaRequestView(BaseModel):
    """所有者可见的请求、最终答案和公开证据。"""

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
