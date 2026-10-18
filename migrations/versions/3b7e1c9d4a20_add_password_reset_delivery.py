"""add password reset delivery encryption and queued mail job

Revision ID: 3b7e1c9d4a20
Revises: 9f4c2a7d1e30
Create Date: 2026-10-18 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3b7e1c9d4a20"
down_revision: str | None = "9f4c2a7d1e30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "password_reset_tokens",
        sa.Column("delivery_ciphertext", sa.Text(), nullable=True),
    )
    op.drop_constraint(op.f("ck_async_jobs_job_type"), "async_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_async_jobs_job_type"),
        "async_jobs",
        "job_type IN ('parse_resume','analyze_resume','generate_questions',"
        "'answer_question','score_open_interview_turn','score_interview_turn',"
        "'advance_interview','generate_report','delete_data','delete_account_data',"
        "'retention_cleanup','password_reset_delivery')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM async_jobs WHERE job_type = 'password_reset_delivery'")
    op.drop_constraint(op.f("ck_async_jobs_job_type"), "async_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_async_jobs_job_type"),
        "async_jobs",
        "job_type IN ('parse_resume','analyze_resume','generate_questions',"
        "'answer_question','score_open_interview_turn','score_interview_turn',"
        "'advance_interview','generate_report','delete_data','delete_account_data',"
        "'retention_cleanup')",
    )
    op.drop_column("password_reset_tokens", "delivery_ciphertext")
