"""add async job request fingerprint

Revision ID: 8f3d2a1c7b90
Revises: 0c7fb95f2e84
Create Date: 2026-10-17 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8f3d2a1c7b90"
down_revision: str | None = "0c7fb95f2e84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Separate hashed idempotency identity from request contents."""

    op.add_column(
        "async_jobs",
        sa.Column("request_fingerprint", sa.Text(), server_default="", nullable=False),
    )


def downgrade() -> None:
    """Remove the request fingerprint."""

    op.drop_column("async_jobs", "request_fingerprint")
