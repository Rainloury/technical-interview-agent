"""add session csrf hash

Revision ID: 0c7fb95f2e84
Revises: 65be64ee0fbe
Create Date: 2026-10-17 20:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0c7fb95f2e84"
down_revision: str | None = "65be64ee0fbe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the server-side CSRF verifier to authenticated sessions."""

    op.add_column("auth_sessions", sa.Column("csrf_token_hash", sa.Text(), nullable=True))
    op.execute("UPDATE auth_sessions SET csrf_token_hash = '' WHERE csrf_token_hash IS NULL")
    op.alter_column("auth_sessions", "csrf_token_hash", nullable=False)


def downgrade() -> None:
    """Remove the CSRF verifier."""

    op.drop_column("auth_sessions", "csrf_token_hash")
