"""add alert delivery evidence

Revision ID: 7e2b4c6d8f10
Revises: 3b7e1c9d4a20
Create Date: 2026-10-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7e2b4c6d8f10"
down_revision: str | None = "3b7e1c9d4a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alert_code", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="critical", nullable=False),
        sa.Column("observed_count", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "alert_code IN ('ready_failed','dead_letter','scoring_failed',"
            "'deletion_failed','worker_heartbeat_stale')",
            name=op.f("ck_alert_deliveries_alert_code"),
        ),
        sa.CheckConstraint(
            "status IN ('delivered','failed')",
            name=op.f("ck_alert_deliveries_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_deliveries")),
    )
    op.create_index(
        "ix_alert_deliveries_code_created",
        "alert_deliveries",
        ["alert_code", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_alert_deliveries_code_created", table_name="alert_deliveries")
    op.drop_table("alert_deliveries")
