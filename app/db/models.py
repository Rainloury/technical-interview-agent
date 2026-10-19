"""SQLAlchemy models for the approved P0 data model."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import JSONBType, UTCDateTime, UUIDType


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(UTCDateTime, nullable=False, server_default=text("now()"))


def _updated_at() -> Mapped[datetime]:
    return mapped_column(
        UTCDateTime, nullable=False, server_default=text("now()"), onupdate=text("now()")
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','suspended','deletion_pending','deleted')",
            name="status",
        ),
        Index("ix_users_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    email_normalized: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index(
            "ix_auth_sessions_user_active",
            "user_id",
            "expires_at",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    last_seen_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    user_agent_hash: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="sessions")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index(
            "ix_password_reset_tokens_user_active",
            "user_id",
            "expires_at",
            postgresql_where=text("used_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    delivery_ciphertext: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ResumeTask(Base):
    __tablename__ = "resume_tasks"
    __table_args__ = (
        CheckConstraint(
            "state IN ('uploaded','extracting','analyzing','generating_questions',"
            "'completed','failed','source_deleted')",
            name="state",
        ),
        Index("ix_resume_tasks_owner_created", "owner_user_id", "created_at"),
        Index("ix_resume_tasks_state_created", "state", "created_at"),
        Index(
            "ix_resume_tasks_expires_active",
            "expires_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default="uploaded")
    failure_stage: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_of_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("resume_tasks.id", ondelete="SET NULL")
    )
    analysis_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("now() + interval '90 days'")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ResumeFile(Base):
    __tablename__ = "resume_files"
    __table_args__ = (
        CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="size_bytes"),
        CheckConstraint(
            "page_count IS NULL OR (page_count >= 1 AND page_count <= 10)",
            name="page_count",
        ),
        CheckConstraint(
            "storage_state IN ('stored','delete_pending','deleted','delete_failed')",
            name="storage_state",
        ),
        Index("ix_resume_files_owner_retention", "owner_user_id", "retention_expires_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    resume_task_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("resume_tasks.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    declared_mime: Mapped[str] = mapped_column(Text, nullable=False)
    detected_mime: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    storage_state: Mapped[str] = mapped_column(String(32), nullable=False, server_default="stored")
    retention_expires_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("now() + interval '30 days'")
    )
    created_at: Mapped[datetime] = _created_at()
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ResumeText(Base):
    __tablename__ = "resume_texts"

    id: Mapped[uuid.UUID] = _pk()
    resume_task_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("resume_tasks.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_version: Mapped[str] = mapped_column(Text, nullable=False)
    page_map: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ResumeAnalysis(Base):
    __tablename__ = "resume_analyses"
    __table_args__ = (Index("ix_resume_analyses_owner_created", "owner_user_id", "created_at"),)

    id: Mapped[uuid.UUID] = _pk()
    resume_task_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("resume_tasks.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_version: Mapped[str] = mapped_column(Text, nullable=False)
    skills: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    projects: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    unverified_items: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    gaps: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("now() + interval '90 days'")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class GeneratedQuestion(Base):
    __tablename__ = "generated_questions"
    __table_args__ = (
        UniqueConstraint("resume_analysis_id", "sequence"),
        CheckConstraint("sequence BETWEEN 1 AND 10", name="sequence"),
        CheckConstraint("difficulty IN ('easy','medium','hard')", name="difficulty"),
        Index("ix_generated_questions_analysis_difficulty", "resume_analysis_id", "difficulty"),
    )

    id: Mapped[uuid.UUID] = _pk()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    resume_analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("resume_analyses.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    topic_key: Mapped[str] = mapped_column(Text, nullable=False)
    assessment_points: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    reference_answer: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_rubric: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    evidence_refs: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        CheckConstraint("source_type IN ('official_doc','question_bank')", name="source_type"),
    )

    id: Mapped[uuid.UUID] = _pk()
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str | None] = mapped_column(String(16))
    allowlisted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = _created_at()


class KnowledgeSourceVersion(Base):
    __tablename__ = "knowledge_source_versions"
    __table_args__ = (
        UniqueConstraint("source_id", "version_label"),
        CheckConstraint("status IN ('draft','published','retired')", name="status"),
    )

    id: Mapped[uuid.UUID] = _pk()
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False
    )
    version_label: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    published_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")


class KnowledgeSourceSection(Base):
    __tablename__ = "knowledge_source_sections"
    __table_args__ = (
        UniqueConstraint("version_id", "section_index"),
        CheckConstraint("section_index >= 0", name="section_index"),
        CheckConstraint("char_length(content) > 0", name="content"),
        Index("ix_knowledge_source_sections_version", "version_id", "section_index"),
    )

    id: Mapped[uuid.UUID] = _pk()
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("knowledge_source_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_path: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class QaRequest(Base):
    __tablename__ = "qa_requests"
    __table_args__ = (
        CheckConstraint(
            "state IN ('created','retrieving','answering','completed','failed')",
            name="state",
        ),
        CheckConstraint(
            "evidence_status IN ('supported','model_knowledge','insufficient')",
            name="evidence_status",
        ),
        CheckConstraint(
            "answer_preference IN ('concise','detailed')",
            name="answer_preference",
        ),
        CheckConstraint("last_event_seq >= 0", name="last_event_seq"),
        Index("ix_qa_requests_owner_created", "owner_user_id", "created_at"),
        Index("ix_qa_requests_state_created", "state", "created_at"),
        Index(
            "uq_qa_requests_owner_idempotency",
            "owner_user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_preference: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="concise"
    )
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default="created")
    answer_json: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    last_event_seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    evidence_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="insufficient"
    )
    extended_questions: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    domain_label: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    saved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class QaStreamEvent(Base):
    __tablename__ = "qa_stream_events"
    __table_args__ = (
        CheckConstraint("seq > 0", name="seq_positive"),
        CheckConstraint(
            "event_type IN ('started','delta','evidence','completed','error')",
            name="event_type",
        ),
        Index(
            "uq_qa_stream_events_terminal",
            "qa_request_id",
            unique=True,
            postgresql_where=text("event_type IN ('completed','error')"),
        ),
    )

    qa_request_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("qa_requests.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class QaEvidence(Base):
    __tablename__ = "qa_evidence"
    __table_args__ = (
        CheckConstraint("char_length(snippet) <= 200", name="snippet_length"),
        CheckConstraint("relevance_score >= 0 AND relevance_score <= 1", name="relevance"),
        CheckConstraint(
            "source_state IN ('available','source_deleted')",
            name="source_state",
        ),
        Index("ix_qa_evidence_qa_request_id", "qa_request_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    qa_request_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("qa_requests.id", ondelete="CASCADE"), nullable=False
    )
    knowledge_source_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("knowledge_source_versions.id", ondelete="SET NULL")
    )
    source_title: Mapped[str] = mapped_column(Text, nullable=False)
    section_path: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    position: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    source_state: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="available"
    )
    created_at: Mapped[datetime] = _created_at()


class Interview(Base):
    __tablename__ = "interviews"
    __table_args__ = (
        CheckConstraint("direction IN ('backend','frontend','fullstack')", name="direction"),
        CheckConstraint(
            "state IN ('created','in_progress','completed','cancelled','timed_out','failed')",
            name="state",
        ),
        CheckConstraint("main_question_count = 5", name="main_question_count"),
        CheckConstraint("total_tokens_used >= 0", name="total_tokens"),
        Index("ix_interviews_owner_created", "owner_user_id", "created_at"),
        Index("ix_interviews_state_deadline", "state", "deadline_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    difficulty_profile: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    topic_keys: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default="created")
    main_question_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    total_token_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    end_reason: Mapped[str | None] = mapped_column(String(32))
    feedback_unlocked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    blueprint_version: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class InterviewTurn(Base):
    __tablename__ = "interview_turns"
    __table_args__ = (
        UniqueConstraint("interview_id", "sequence"),
        CheckConstraint("depth BETWEEN 0 AND 2", name="depth"),
        CheckConstraint(
            "turn_type IN ('main','follow_up') AND "
            "((turn_type = 'main' AND depth = 0) OR "
            "(turn_type = 'follow_up' AND depth BETWEEN 1 AND 2))",
            name="turn_type_depth",
        ),
        CheckConstraint(
            "state IN ('pending','awaiting_answer','scoring','passed','failed',"
            "'scoring_failed','branch_completed','skipped','unanswered','cancelled')",
            name="state",
        ),
        CheckConstraint("difficulty IN ('easy','medium','hard')", name="difficulty"),
        Index("ix_interview_turns_owner_interview", "owner_user_id", "interview_id"),
        Index(
            "ix_interview_turns_interview_parent_seq",
            "interview_id",
            "parent_turn_id",
            "sequence",
        ),
        Index(
            "uq_interview_turns_idempotency",
            "interview_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    parent_turn_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("interview_turns.id", ondelete="SET NULL")
    )
    root_turn_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    turn_type: Mapped[str] = mapped_column(String(16), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    end_reason: Mapped[str | None] = mapped_column(String(32))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    reference_answer: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_rubric: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    topic_key: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    question_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    answer_text: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    score_total: Mapped[float | None] = mapped_column(Numeric(5, 2))
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    score_band: Mapped[str | None] = mapped_column(String(16))
    critical_error: Mapped[bool | None] = mapped_column(Boolean)
    score_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class InterviewOperation(Base):
    __tablename__ = "interview_operations"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('start','skip','end_branch')",
            name="operation",
        ),
        UniqueConstraint(
            "owner_user_id",
            "interview_id",
            "operation",
            "idempotency_key",
            name="owner_interview_operation_key",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class FollowUpChain(Base):
    __tablename__ = "follow_up_chains"
    __table_args__ = (
        UniqueConstraint("interview_id", "root_turn_id"),
        CheckConstraint("depth_used BETWEEN 0 AND max_depth", name="depth_used"),
        CheckConstraint("answer_count BETWEEN 0 AND max_answers", name="answer_count"),
        CheckConstraint("tokens_used >= 0 AND tokens_used <= token_budget", name="tokens"),
        Index("ix_follow_up_chains_state_updated", "state", "updated_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False
    )
    root_turn_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("interview_turns.id", ondelete="CASCADE"), nullable=False
    )
    current_turn_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("interview_turns.id", ondelete="SET NULL")
    )
    depth_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    answer_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_depth: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2")
    max_answers: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    token_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default="awaiting_answer")
    termination_reason: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = _updated_at()


class ScoringAttempt(Base):
    __tablename__ = "scoring_attempts"
    __table_args__ = (
        UniqueConstraint("turn_id", "attempt_no"),
        CheckConstraint(
            "state IN ('pending','running','succeeded','failed','timed_out')",
            name="state",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    turn_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("interview_turns.id", ondelete="CASCADE"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    raw_output: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    validated_output: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    error_code: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = _created_at()


class InterviewReport(Base):
    __tablename__ = "interview_reports"

    id: Mapped[uuid.UUID] = _pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    main_question_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    follow_up_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    passed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    topic_performance: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    report_version: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = _created_at()
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class WrongQuestion(Base):
    __tablename__ = "wrong_questions"
    __table_args__ = (
        CheckConstraint("difficulty IN ('easy','medium','hard')", name="difficulty"),
        CheckConstraint(
            "state IN ('active','reviewing','mastered','archived')",
            name="state",
        ),
        Index("ix_wrong_questions_owner_state_created", "owner_user_id", "state", "created_at"),
        Index(
            "ix_wrong_questions_owner_topic_difficulty",
            "owner_user_id",
            "topic_key",
            "difficulty",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("interview_turns.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    parent_turn_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    reference_answer: Mapped[str] = mapped_column(Text, nullable=False)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    loss_reasons: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    topic_key: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class WeakPoint(Base):
    __tablename__ = "weak_points"
    __table_args__ = (
        CheckConstraint(
            "state IN ('identified','reviewing','improved','archived')",
            name="state",
        ),
        Index(
            "uq_weak_points_owner_topic_active",
            "owner_user_id",
            "topic_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_weak_points_owner_order",
            "owner_user_id",
            "severity",
            "failure_count",
            "last_failure_at",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    topic_key: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_failure_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    review_advice: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="identified")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class WeakPointEvidence(Base):
    __tablename__ = "weak_point_evidence"
    __table_args__ = (
        UniqueConstraint(
            "weak_point_id",
            "wrong_question_id",
            "turn_id",
            "loss_reason_hash",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    weak_point_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("weak_points.id", ondelete="CASCADE"), nullable=False
    )
    wrong_question_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("wrong_questions.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("interview_turns.id", ondelete="CASCADE"), nullable=False
    )
    loss_reason_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class AsyncJob(Base):
    __tablename__ = "async_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('parse_resume','analyze_resume','generate_questions',"
            "'answer_question','score_open_interview_turn','score_interview_turn',"
            "'advance_interview','generate_report','delete_data','delete_account_data',"
            "'retention_cleanup','password_reset_delivery')",
            name="job_type",
        ),
        CheckConstraint(
            "state IN ('queued','leased','succeeded','failed','dead_letter','cancelled')",
            name="state",
        ),
        CheckConstraint("fencing_token >= 0", name="fencing_token"),
        Index("ix_async_jobs_state_next_run", "state", "next_run_at"),
        Index(
            "ix_async_jobs_lease_until",
            "lease_until",
            postgresql_where=text("state = 'leased'"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL")
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    request_fingerprint: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="", default=""
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(Text)
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    next_run_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("now()")
    )
    error_code: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("result IN ('success','failure','denied')", name="result"),
        CheckConstraint("expires_at = created_at + interval '365 days'", name="retention"),
        UniqueConstraint(
            "request_id",
            "action",
            "resource_type",
            "resource_id_hash",
        ),
        Index("ix_audit_events_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id_hash: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("now() + interval '365 days'")
    )


class DataDeletionRequest(Base):
    __tablename__ = "data_deletion_requests"
    __table_args__ = (
        CheckConstraint(
            "state IN ('requested','deleting','completed','failed')",
            name="state",
        ),
        UniqueConstraint(
            "owner_user_id",
            "idempotency_key",
            name="owner_idempotency_key",
        ),
        Index(
            "ix_data_deletion_requests_owner_created",
            "owner_user_id",
            "created_at",
        ),
        Index("ix_data_deletion_requests_state_updated", "state", "updated_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="requested")
    scope: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"
    __table_args__ = (
        CheckConstraint(
            "alert_code IN ('ready_failed','dead_letter','scoring_failed',"
            "'deletion_failed','worker_heartbeat_stale')",
            name="alert_code",
        ),
        CheckConstraint("status IN ('delivered','failed')", name="status"),
        Index("ix_alert_deliveries_code_created", "alert_code", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    alert_code: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, server_default="critical")
    observed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
