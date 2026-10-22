"""add private document RAG schema

Revision ID: 7f3a9c2d1b40
Revises: 7e2b4c6d8f10
Create Date: 2026-10-21 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "7f3a9c2d1b40"
down_revision: str | None = "7e2b4c6d8f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "user_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
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
        sa.Column(
            "retention_expires_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now() + interval '90 days'"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('uploaded','processing','ready','failed','deleted')",
            name=op.f("ck_user_documents_state"),
        ),
        sa.CheckConstraint(
            "deletion_state IS NULL OR deletion_state IN ('pending','deleted','failed')",
            name=op.f("ck_user_documents_deletion_state"),
        ),
        sa.CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 10485760",
            name=op.f("ck_user_documents_size_bytes"),
        ),
        sa.CheckConstraint("chunk_count >= 0", name=op.f("ck_user_documents_chunk_count")),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_user_documents_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_documents")),
        sa.UniqueConstraint("object_key", name=op.f("uq_user_documents_object_key")),
    )
    op.create_index(
        "ix_user_documents_owner_created",
        "user_documents",
        ["owner_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_documents_owner_state_updated",
        "user_documents",
        ["owner_user_id", "state", "updated_at"],
        unique=False,
    )
    op.create_index(
        "uq_user_documents_owner_sha",
        "user_documents",
        ["owner_user_id", "sha256"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_user_documents_owner_idempotency",
        "user_documents",
        ["owner_user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "user_document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint("chunk_index >= 0", name=op.f("ck_user_document_chunks_chunk_index")),
        sa.CheckConstraint("token_count > 0", name=op.f("ck_user_document_chunks_token_count")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["user_documents.id"],
            name=op.f("fk_user_document_chunks_document_id_user_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_user_document_chunks_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_document_chunks")),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name=op.f("uq_user_document_chunks_document_id"),
        ),
    )
    op.create_index(
        "ix_user_document_chunks_owner_document",
        "user_document_chunks",
        ["owner_user_id", "document_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_document_chunks_search_vector",
        "user_document_chunks",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_user_document_chunks_embedding_hnsw",
        "user_document_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.add_column("knowledge_source_sections", sa.Column("embedding", Vector(1024)))
    op.add_column("knowledge_source_sections", sa.Column("embedding_model", sa.Text()))
    op.add_column("knowledge_source_sections", sa.Column("embedding_dimensions", sa.Integer()))
    op.add_column("knowledge_source_sections", sa.Column("embedding_index_version", sa.Text()))
    op.add_column(
        "knowledge_source_sections",
        sa.Column("search_text", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "knowledge_source_sections",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', search_text)", persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_knowledge_source_sections_search_vector",
        "knowledge_source_sections",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_knowledge_source_sections_embedding_hnsw",
        "knowledge_source_sections",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.add_column(
        "qa_evidence",
        sa.Column(
            "source_kind",
            sa.String(length=32),
            server_default="system",
            nullable=False,
        ),
    )
    op.add_column("qa_evidence", sa.Column("user_document_chunk_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_qa_evidence_user_document_chunk_id_user_document_chunks"),
        "qa_evidence",
        "user_document_chunks",
        ["user_document_chunk_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(op.f("ck_async_jobs_job_type"), "async_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_async_jobs_job_type"),
        "async_jobs",
        "job_type IN ('parse_resume','analyze_resume','generate_questions',"
        "'answer_question','score_open_interview_turn','score_interview_turn',"
        "'advance_interview','generate_report','delete_data','delete_account_data',"
        "'retention_cleanup','password_reset_delivery','process_document','delete_document')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_async_jobs_job_type"), "async_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_async_jobs_job_type"),
        "async_jobs",
        "job_type IN ('parse_resume','analyze_resume','generate_questions',"
        "'answer_question','score_open_interview_turn','score_interview_turn',"
        "'advance_interview','generate_report','delete_data','delete_account_data',"
        "'retention_cleanup','password_reset_delivery')",
    )
    op.drop_constraint(
        op.f("fk_qa_evidence_user_document_chunk_id_user_document_chunks"),
        "qa_evidence",
        type_="foreignkey",
    )
    op.drop_column("qa_evidence", "user_document_chunk_id")
    op.drop_column("qa_evidence", "source_kind")

    op.drop_index(
        "ix_knowledge_source_sections_embedding_hnsw",
        table_name="knowledge_source_sections",
    )
    op.drop_index(
        "ix_knowledge_source_sections_search_vector",
        table_name="knowledge_source_sections",
    )
    op.drop_column("knowledge_source_sections", "search_vector")
    op.drop_column("knowledge_source_sections", "search_text")
    op.drop_column("knowledge_source_sections", "embedding_index_version")
    op.drop_column("knowledge_source_sections", "embedding_dimensions")
    op.drop_column("knowledge_source_sections", "embedding_model")
    op.drop_column("knowledge_source_sections", "embedding")

    op.drop_index(
        "ix_user_document_chunks_embedding_hnsw",
        table_name="user_document_chunks",
    )
    op.drop_index(
        "ix_user_document_chunks_search_vector",
        table_name="user_document_chunks",
    )
    op.drop_index(
        "ix_user_document_chunks_owner_document",
        table_name="user_document_chunks",
    )
    op.drop_table("user_document_chunks")

    op.drop_index("uq_user_documents_owner_idempotency", table_name="user_documents")
    op.drop_index("uq_user_documents_owner_sha", table_name="user_documents")
    op.drop_index("ix_user_documents_owner_state_updated", table_name="user_documents")
    op.drop_index("ix_user_documents_owner_created", table_name="user_documents")
    op.drop_table("user_documents")
