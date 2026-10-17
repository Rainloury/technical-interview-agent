"""add QA retrieval slice

Revision ID: 4b6e9d2c1a70
Revises: 8f3d2a1c7b90
Create Date: 2026-10-17 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4b6e9d2c1a70"
down_revision: str | None = "8f3d2a1c7b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add knowledge sections, QA idempotency, and the answer job type."""

    op.create_table(
        "knowledge_source_sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("section_index", sa.Integer(), nullable=False),
        sa.Column("section_path", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "section_index >= 0",
            name=op.f("ck_knowledge_source_sections_section_index"),
        ),
        sa.CheckConstraint(
            "char_length(content) > 0",
            name=op.f("ck_knowledge_source_sections_content"),
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["knowledge_source_versions.id"],
            name=op.f("fk_knowledge_source_sections_version_id_knowledge_source_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_source_sections")),
        sa.UniqueConstraint(
            "version_id",
            "section_index",
            name=op.f("uq_knowledge_source_sections_version_id"),
        ),
    )
    op.create_index(
        "ix_knowledge_source_sections_version",
        "knowledge_source_sections",
        ["version_id", "section_index"],
        unique=False,
    )
    op.add_column(
        "qa_requests",
        sa.Column(
            "answer_preference",
            sa.String(length=16),
            server_default="concise",
            nullable=False,
        ),
    )
    op.add_column("qa_requests", sa.Column("idempotency_key", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_qa_requests_answer_preference"),
        "qa_requests",
        "answer_preference IN ('concise','detailed')",
    )
    op.create_index(
        "uq_qa_requests_owner_idempotency",
        "qa_requests",
        ["owner_user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_index(
        "uq_qa_stream_events_completed",
        table_name="qa_stream_events",
        postgresql_where=sa.text("event_type = 'completed'"),
    )
    op.drop_index(
        "uq_qa_stream_events_error",
        table_name="qa_stream_events",
        postgresql_where=sa.text("event_type = 'error'"),
    )
    op.create_index(
        "uq_qa_stream_events_terminal",
        "qa_stream_events",
        ["qa_request_id"],
        unique=True,
        postgresql_where=sa.text("event_type IN ('completed','error')"),
    )
    op.drop_constraint(op.f("ck_async_jobs_job_type"), "async_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_async_jobs_job_type"),
        "async_jobs",
        "job_type IN ('parse_resume','analyze_resume','generate_questions',"
        "'answer_question','score_answer','generate_report','delete_data')",
    )


def downgrade() -> None:
    """Remove the QA retrieval additions without touching historical QA rows."""

    op.drop_constraint(op.f("ck_async_jobs_job_type"), "async_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_async_jobs_job_type"),
        "async_jobs",
        "job_type IN ('parse_resume','analyze_resume','generate_questions',"
        "'score_answer','generate_report','delete_data')",
    )
    op.drop_index(
        "uq_qa_stream_events_terminal",
        table_name="qa_stream_events",
        postgresql_where=sa.text("event_type IN ('completed','error')"),
    )
    op.create_index(
        "uq_qa_stream_events_completed",
        "qa_stream_events",
        ["qa_request_id"],
        unique=True,
        postgresql_where=sa.text("event_type = 'completed'"),
    )
    op.create_index(
        "uq_qa_stream_events_error",
        "qa_stream_events",
        ["qa_request_id"],
        unique=True,
        postgresql_where=sa.text("event_type = 'error'"),
    )
    op.drop_index(
        "uq_qa_requests_owner_idempotency",
        table_name="qa_requests",
    )
    op.drop_constraint(
        op.f("ck_qa_requests_answer_preference"),
        "qa_requests",
        type_="check",
    )
    op.drop_column("qa_requests", "idempotency_key")
    op.drop_column("qa_requests", "answer_preference")
    op.drop_index(
        "ix_knowledge_source_sections_version",
        table_name="knowledge_source_sections",
    )
    op.drop_table("knowledge_source_sections")
