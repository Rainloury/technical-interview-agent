"""add interview advance job type

Revision ID: 7d1a3e5b9c42
Revises: 2c9e7f4a1b60
Create Date: 2026-10-18 12:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7d1a3e5b9c42"
down_revision: str | None = "2c9e7f4a1b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_async_jobs_job_type"), "async_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_async_jobs_job_type"),
        "async_jobs",
        "job_type IN ('parse_resume','analyze_resume','generate_questions',"
        "'answer_question','score_open_interview_turn','score_interview_turn',"
        "'advance_interview','generate_report','delete_data')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM async_jobs WHERE job_type = 'advance_interview'")
    op.drop_constraint(op.f("ck_async_jobs_job_type"), "async_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_async_jobs_job_type"),
        "async_jobs",
        "job_type IN ('parse_resume','analyze_resume','generate_questions',"
        "'answer_question','score_open_interview_turn','score_interview_turn',"
        "'generate_report','delete_data')",
    )
