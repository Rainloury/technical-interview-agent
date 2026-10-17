"""add interview and review slice

Revision ID: 2c9e7f4a1b60
Revises: 4b6e9d2c1a70
Create Date: 2026-10-18 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2c9e7f4a1b60"
down_revision: str | None = "4b6e9d2c1a70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add operation idempotency and interview scoring job types."""

    op.create_table(
        "interview_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=24), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation IN ('start','skip','end_branch')",
            name=op.f("ck_interview_operations_operation"),
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_interview_operations_interview_id_interviews"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_interview_operations_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_operations")),
        sa.UniqueConstraint(
            "owner_user_id",
            "interview_id",
            "operation",
            "idempotency_key",
            name=op.f("owner_interview_operation_key"),
        ),
    )
    op.drop_constraint(op.f("ck_async_jobs_job_type"), "async_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_async_jobs_job_type"),
        "async_jobs",
        "job_type IN ('parse_resume','analyze_resume','generate_questions',"
        "'answer_question','score_open_interview_turn','score_interview_turn',"
        "'advance_interview','generate_report','delete_data')",
    )


def downgrade() -> None:
    """Remove interview operation records and restore the prior job enum."""

    op.execute(
        "DELETE FROM async_jobs "
        "WHERE job_type IN ('score_open_interview_turn','score_interview_turn','advance_interview')"
    )
    op.drop_constraint(op.f("ck_async_jobs_job_type"), "async_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_async_jobs_job_type"),
        "async_jobs",
        "job_type IN ('parse_resume','analyze_resume','generate_questions',"
        "'answer_question','score_answer','generate_report','delete_data')",
    )
    op.drop_table("interview_operations")
