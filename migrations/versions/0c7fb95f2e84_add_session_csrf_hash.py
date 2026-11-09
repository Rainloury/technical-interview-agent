"""添加会话 csrf 哈希

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
    """将服务端 CSRF 验证器添加到已认证会话中。"""

    op.add_column("auth_sessions", sa.Column("csrf_token_hash", sa.Text(), nullable=True))
    op.execute("UPDATE auth_sessions SET csrf_token_hash = '' WHERE csrf_token_hash IS NULL")
    op.alter_column("auth_sessions", "csrf_token_hash", nullable=False)


def downgrade() -> None:
    """移除 CSRF 验证器。"""

    op.drop_column("auth_sessions", "csrf_token_hash")
