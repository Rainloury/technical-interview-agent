"""add privacy lifecycle

Revision ID: 9f4c2a7d1e30
Revises: 7d1a3e5b9c42
Create Date: 2026-10-18 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9f4c2a7d1e30"
down_revision: str | None = "7d1a3e5b9c42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_deletion_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="requested", nullable=False),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('requested','deleting','completed','failed')",
            name=op.f("ck_data_deletion_requests_state"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_data_deletion_requests_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_deletion_requests")),
        sa.UniqueConstraint(
            "owner_user_id",
            "idempotency_key",
            name=op.f("owner_idempotency_key"),
        ),
    )
    op.create_index(
        "ix_data_deletion_requests_owner_created",
        "data_deletion_requests",
        ["owner_user_id", "created_at"],
    )
    op.create_index(
        "ix_data_deletion_requests_state_updated",
        "data_deletion_requests",
        ["state", "updated_at"],
    )
    op.drop_constraint(op.f("ck_async_jobs_job_type"), "async_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_async_jobs_job_type"),
        "async_jobs",
        "job_type IN ('parse_resume','analyze_resume','generate_questions',"
        "'answer_question','score_open_interview_turn','score_interview_turn',"
        "'advance_interview','generate_report','delete_data','delete_account_data',"
        "'retention_cleanup')",
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM async_jobs WHERE job_type IN ('delete_account_data','retention_cleanup')"
    )
    op.drop_constraint(op.f("ck_async_jobs_job_type"), "async_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_async_jobs_job_type"),
        "async_jobs",
        "job_type IN ('parse_resume','analyze_resume','generate_questions',"
        "'answer_question','score_open_interview_turn','score_interview_turn',"
        "'advance_interview','generate_report','delete_data')",
    )
    op.drop_index(
        "ix_data_deletion_requests_state_updated",
        table_name="data_deletion_requests",
    )
    op.drop_index(
        "ix_data_deletion_requests_owner_created",
        table_name="data_deletion_requests",
    )
    op.drop_table("data_deletion_requests")
