"""add shared documents and admin roles

Revision ID: 1b5d8e3f7a20
Revises: 7f3a9c2d1b40
Create Date: 2026-10-22 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "1b5d8e3f7a20"
down_revision: str | None = "7f3a9c2d1b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "users",
        sa.Column("role", sa.String(length=16), server_default="user", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_users_role"),
        "users",
        "role IN ('user','admin')",
    )

    op.create_table(
        "shared_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("detected_mime", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=32), server_default="uploaded", nullable=False),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("index_version", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("request_fingerprint", sa.Text(), nullable=True),
        sa.Column("deletion_state", sa.String(length=16), nullable=True),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('uploaded','processing','ready','failed','deleted')",
            name=op.f("ck_shared_documents_state"),
        ),
        sa.CheckConstraint(
            "deletion_state IS NULL OR deletion_state IN ('pending','deleted','failed')",
            name=op.f("ck_shared_documents_deletion_state"),
        ),
        sa.CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 10485760",
            name=op.f("ck_shared_documents_size_bytes"),
        ),
        sa.CheckConstraint(
            "chunk_count >= 0",
            name=op.f("ck_shared_documents_chunk_count"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_shared_documents_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shared_documents")),
        sa.UniqueConstraint("object_key", name=op.f("uq_shared_documents_object_key")),
    )
    op.create_index(
        "ix_shared_documents_created",
        "shared_documents",
        ["created_at", "id"],
    )
    op.create_index(
        "ix_shared_documents_state_updated",
        "shared_documents",
        ["state", "updated_at"],
    )
    op.create_index(
        "uq_shared_documents_sha",
        "shared_documents",
        ["sha256"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_shared_documents_idempotency",
        "shared_documents",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "shared_document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section_path", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', search_text)", persisted=True),
            nullable=False,
        ),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name=op.f("ck_shared_document_chunks_chunk_index"),
        ),
        sa.CheckConstraint(
            "token_count > 0",
            name=op.f("ck_shared_document_chunks_token_count"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["shared_documents.id"],
            name=op.f("fk_shared_document_chunks_document_id_shared_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shared_document_chunks")),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name=op.f("uq_shared_document_chunks_document_id"),
        ),
    )
    op.create_index(
        "ix_shared_document_chunks_document",
        "shared_document_chunks",
        ["document_id"],
    )
    op.create_index(
        "ix_shared_document_chunks_search_vector",
        "shared_document_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_shared_document_chunks_embedding_hnsw",
        "shared_document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.add_column(
        "qa_evidence",
        sa.Column("shared_document_chunk_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_qa_evidence_shared_document_chunk_id_shared_document_chunks"),
        "qa_evidence",
        "shared_document_chunks",
        ["shared_document_chunk_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        op.f("ck_qa_evidence_source_kind"),
        "qa_evidence",
        "source_kind IN ('system','user_document','shared_document')",
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_shared_document_admin_creator()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.created_by_user_id IS NOT NULL THEN
                IF NOT EXISTS (
                    SELECT 1 FROM users
                    WHERE id = NEW.created_by_user_id AND role = 'admin'
                ) THEN
                    RAISE EXCEPTION 'shared document creator must be an admin'
                        USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_shared_document_admin_creator
        BEFORE INSERT OR UPDATE OF created_by_user_id ON shared_documents
        FOR EACH ROW EXECUTE FUNCTION enforce_shared_document_admin_creator();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_shared_document_admin_creator ON shared_documents")
    op.execute("DROP FUNCTION IF EXISTS enforce_shared_document_admin_creator()")
    op.drop_constraint(op.f("ck_qa_evidence_source_kind"), "qa_evidence", type_="check")
    op.drop_constraint(
        op.f("fk_qa_evidence_shared_document_chunk_id_shared_document_chunks"),
        "qa_evidence",
        type_="foreignkey",
    )
    op.drop_column("qa_evidence", "shared_document_chunk_id")
    op.drop_index(
        "ix_shared_document_chunks_embedding_hnsw",
        table_name="shared_document_chunks",
    )
    op.drop_index(
        "ix_shared_document_chunks_search_vector",
        table_name="shared_document_chunks",
    )
    op.drop_index(
        "ix_shared_document_chunks_document",
        table_name="shared_document_chunks",
    )
    op.drop_table("shared_document_chunks")
    op.drop_index("uq_shared_documents_idempotency", table_name="shared_documents")
    op.drop_index("uq_shared_documents_sha", table_name="shared_documents")
    op.drop_index("ix_shared_documents_state_updated", table_name="shared_documents")
    op.drop_index("ix_shared_documents_created", table_name="shared_documents")
    op.drop_table("shared_documents")
    op.drop_constraint(op.f("ck_users_role"), "users", type_="check")
    op.drop_column("users", "role")
