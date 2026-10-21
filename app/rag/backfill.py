"""Idempotent backfill of embeddings for allowlisted system knowledge."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import (
    KnowledgeSource,
    KnowledgeSourceSection,
    KnowledgeSourceVersion,
)
from app.rag.ollama import EmbeddingClient

BACKFILL_INDEX_VERSION = "rag-v1"


@dataclass(frozen=True, slots=True)
class BackfillResult:
    """Counts for one bounded backfill run."""

    processed: int
    skipped: int
    failed: int


async def _latest_sections(session: AsyncSession) -> list[KnowledgeSourceSection]:
    latest = (
        select(
            KnowledgeSourceVersion.id.label("version_id"),
            KnowledgeSourceVersion.source_id.label("source_id"),
        )
        .join(KnowledgeSource, KnowledgeSource.id == KnowledgeSourceVersion.source_id)
        .where(
            KnowledgeSource.allowlisted.is_(True),
            KnowledgeSourceVersion.status == "published",
        )
        .distinct(KnowledgeSourceVersion.source_id)
        .order_by(
            KnowledgeSourceVersion.source_id,
            KnowledgeSourceVersion.published_at.desc(),
            KnowledgeSourceVersion.id.desc(),
        )
        .subquery()
    )
    return list(
        (
            await session.execute(
                select(KnowledgeSourceSection)
                .join(latest, latest.c.version_id == KnowledgeSourceSection.version_id)
                .order_by(KnowledgeSourceSection.id)
            )
        ).scalars()
    )


async def backfill_system_embeddings(
    session: AsyncSession,
    *,
    embedding_client: EmbeddingClient,
    settings: Settings,
    batch_size: int = 16,
) -> BackfillResult:
    """Backfill one bounded pass without touching frozen QA evidence."""

    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    sections = await _latest_sections(session)
    pending = [
        section
        for section in sections
        if section.embedding is None
        or section.embedding_index_version != BACKFILL_INDEX_VERSION
    ]
    skipped = len(sections) - len(pending)
    processed = 0
    failed = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        try:
            vectors = await embedding_client.embed([section.content for section in batch])
            if len(vectors) != len(batch):
                raise ValueError("embedding count mismatch")
            for section, vector in zip(batch, vectors, strict=True):
                if len(vector) != settings.ollama_embedding_dimensions:
                    raise ValueError("embedding dimension mismatch")
                section.embedding = vector
                section.embedding_model = settings.ollama_embedding_model
                section.embedding_dimensions = settings.ollama_embedding_dimensions
                section.embedding_index_version = BACKFILL_INDEX_VERSION
            await session.commit()
            processed += len(batch)
        except Exception:
            await session.rollback()
            failed += len(batch)
    return BackfillResult(processed=processed, skipped=skipped, failed=failed)
