"""Hybrid pgvector/lexical retrieval with deterministic RRF fusion."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Subquery

from app.db.models import (
    KnowledgeSource,
    KnowledgeSourceSection,
    KnowledgeSourceVersion,
    SharedDocument,
    SharedDocumentChunk,
    UserDocument,
    UserDocumentChunk,
)
from app.qa_contracts import tokenize
from app.rag.ollama import EmbeddingClient


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    """One hit from either recall route."""

    kind: Literal["vector", "lexical"]
    chunk_id: uuid.UUID
    source_kind: Literal["system", "user_document", "shared_document"]
    title: str
    section_path: str
    snippet: str
    score: float
    knowledge_source_version_id: uuid.UUID | None = None
    user_document_chunk_id: uuid.UUID | None = None
    shared_document_chunk_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class MergedEvidence:
    """Fused, owner-safe evidence ready to freeze in qa_evidence."""

    chunk_id: uuid.UUID
    user_document_chunk_id: uuid.UUID | None
    shared_document_chunk_id: uuid.UUID | None
    knowledge_source_version_id: uuid.UUID | None
    source_kind: Literal["system", "user_document", "shared_document"]
    title: str
    section_path: str
    snippet: str
    relevance_score: float
    position: dict[str, int | str]


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """Evidence plus vector-route status for observability and degradation."""

    evidence: list[MergedEvidence]
    vector_status: Literal["ok", "degraded", "disabled"]
    vector_error_code: str | None = None


def _fused_score(rank: int, k: int) -> float:
    return 1.0 / (k + rank)


def rrf_merge(
    vector: list[SearchCandidate],
    lexical: list[SearchCandidate],
    *,
    k: int = 60,
    limit: int = 5,
) -> list[MergedEvidence]:
    """Fuse two ranked lists with reciprocal-rank fusion and stable ties."""

    by_id: dict[uuid.UUID, tuple[SearchCandidate, float]] = {}
    for route in (vector, lexical):
        for rank, candidate in enumerate(route, start=1):
            existing = by_id.get(candidate.chunk_id)
            score = _fused_score(rank, k)
            if existing is None:
                by_id[candidate.chunk_id] = (candidate, score)
            else:
                by_id[candidate.chunk_id] = (existing[0], existing[1] + score)
    ranked = sorted(
        by_id.values(),
        key=lambda item: (
            -item[1],
            0 if item[0].source_kind == "system" else 1,
            item[0].source_kind,
            item[0].title,
            item[0].section_path,
            str(item[0].chunk_id),
        ),
    )
    selected = ranked[:limit]
    return [
        MergedEvidence(
            chunk_id=candidate.chunk_id,
            user_document_chunk_id=(
                candidate.user_document_chunk_id
                if candidate.source_kind == "user_document"
                else None
            ),
            shared_document_chunk_id=(
                candidate.shared_document_chunk_id
                if candidate.source_kind == "shared_document"
                else None
            ),
            knowledge_source_version_id=candidate.knowledge_source_version_id,
            source_kind=candidate.source_kind,
            title=candidate.title,
            section_path=candidate.section_path,
            snippet=candidate.snippet[:200],
            relevance_score=round(score, 6),
            position={"rank": rank, "citation_id": f"evidence-{rank}"},
        )
        for rank, (candidate, score) in enumerate(selected, start=1)
    ]


async def hybrid_retrieve(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    question: str,
    embedding_client: EmbeddingClient | None,
    limit: int = 5,
) -> RetrievalResult:
    """Retrieve owner-scoped personal and allowlisted system evidence."""

    terms = _lexical_terms(question)
    lexical: list[SearchCandidate] = []
    if terms:
        user_rows = (
            await session.execute(
                select(UserDocumentChunk, UserDocument.title)
                .join(UserDocument, UserDocument.id == UserDocumentChunk.document_id)
                .where(
                    UserDocumentChunk.owner_user_id == owner_user_id,
                    UserDocument.owner_user_id == owner_user_id,
                    UserDocument.state == "ready",
                    UserDocument.deleted_at.is_(None),
                    UserDocumentChunk.search_vector.op("@@")(_tsquery(terms)),
                )
                .order_by(
                    func.ts_rank_cd(
                        UserDocumentChunk.search_vector,
                        _tsquery(terms),
                    ).desc(),
                    UserDocumentChunk.id,
                )
                .limit(20)
            )
        ).all()
        lexical.extend(
            SearchCandidate(
                kind="lexical",
                chunk_id=chunk.id,
                source_kind="user_document",
                title=title,
                section_path=chunk.section_path,
                snippet=_snippet(chunk.content, terms),
                score=1.0,
                user_document_chunk_id=chunk.id,
            )
            for chunk, title in user_rows
        )
        shared_rows = (
            await session.execute(
                select(SharedDocumentChunk, SharedDocument.title)
                .join(SharedDocument, SharedDocument.id == SharedDocumentChunk.document_id)
                .where(
                    SharedDocument.state == "ready",
                    SharedDocument.deleted_at.is_(None),
                    SharedDocumentChunk.search_vector.op("@@")(_tsquery(terms)),
                )
                .order_by(
                    func.ts_rank_cd(
                        SharedDocumentChunk.search_vector,
                        _tsquery(terms),
                    ).desc(),
                    SharedDocumentChunk.id,
                )
                .limit(20)
            )
        ).all()
        lexical.extend(
            SearchCandidate(
                kind="lexical",
                chunk_id=chunk.id,
                source_kind="shared_document",
                title=title,
                section_path=chunk.section_path,
                snippet=_snippet(chunk.content, terms),
                score=1.0,
                shared_document_chunk_id=chunk.id,
            )
            for chunk, title in shared_rows
        )
        latest_system = _latest_system_versions()
        system_rows = (
            await session.execute(
                select(
                    KnowledgeSourceSection,
                    KnowledgeSource.title,
                    KnowledgeSourceVersion.id,
                )
                .join(
                    KnowledgeSourceVersion,
                    KnowledgeSourceVersion.id == KnowledgeSourceSection.version_id,
                )
                .join(KnowledgeSource, KnowledgeSource.id == KnowledgeSourceVersion.source_id)
                .join(latest_system, latest_system.c.version_id == KnowledgeSourceVersion.id)
                .where(
                    KnowledgeSource.allowlisted.is_(True),
                    KnowledgeSourceVersion.status == "published",
                    KnowledgeSourceSection.search_vector.op("@@")(_tsquery(terms)),
                )
                .order_by(
                    func.ts_rank_cd(
                        KnowledgeSourceSection.search_vector,
                        _tsquery(terms),
                    ).desc(),
                    KnowledgeSourceSection.id,
                )
                .limit(20)
            )
        ).all()
        lexical.extend(
            SearchCandidate(
                kind="lexical",
                chunk_id=section.id,
                source_kind="system",
                title=title,
                section_path=section.section_path,
                snippet=_snippet(section.content, terms),
                score=1.0,
                knowledge_source_version_id=version_id,
            )
            for section, title, version_id in system_rows
        )

    vector: list[SearchCandidate] = []
    vector_status: Literal["ok", "degraded", "disabled"] = (
        "disabled" if embedding_client is None else "ok"
    )
    vector_error_code: str | None = None
    if embedding_client is not None:
        try:
            query_vector = (await embedding_client.embed([question]))[0]
            user_vectors = (
                await session.execute(
                    select(UserDocumentChunk, UserDocument.title)
                    .join(UserDocument, UserDocument.id == UserDocumentChunk.document_id)
                    .where(
                        UserDocumentChunk.owner_user_id == owner_user_id,
                        UserDocument.owner_user_id == owner_user_id,
                        UserDocument.state == "ready",
                        UserDocument.deleted_at.is_(None),
                    )
                    .order_by(UserDocumentChunk.embedding.cosine_distance(query_vector))
                    .limit(20)
                )
            ).all()
            vector.extend(
                SearchCandidate(
                    kind="vector",
                    chunk_id=chunk.id,
                    source_kind="user_document",
                    title=title,
                    section_path=chunk.section_path,
                    snippet=_snippet(chunk.content, terms),
                    score=1.0,
                    user_document_chunk_id=chunk.id,
                )
                for chunk, title in user_vectors
            )
            shared_vectors = (
                await session.execute(
                    select(SharedDocumentChunk, SharedDocument.title)
                    .join(SharedDocument, SharedDocument.id == SharedDocumentChunk.document_id)
                    .where(
                        SharedDocument.state == "ready",
                        SharedDocument.deleted_at.is_(None),
                    )
                    .order_by(SharedDocumentChunk.embedding.cosine_distance(query_vector))
                    .limit(20)
                )
            ).all()
            vector.extend(
                SearchCandidate(
                    kind="vector",
                    chunk_id=chunk.id,
                    source_kind="shared_document",
                    title=title,
                    section_path=chunk.section_path,
                    snippet=_snippet(chunk.content, terms),
                    score=1.0,
                    shared_document_chunk_id=chunk.id,
                )
                for chunk, title in shared_vectors
            )
            latest_system = _latest_system_versions()
            system_vectors = (
                await session.execute(
                    select(
                        KnowledgeSourceSection,
                        KnowledgeSource.title,
                        KnowledgeSourceVersion.id,
                    )
                    .join(
                        KnowledgeSourceVersion,
                        KnowledgeSourceVersion.id == KnowledgeSourceSection.version_id,
                    )
                    .join(KnowledgeSource, KnowledgeSource.id == KnowledgeSourceVersion.source_id)
                    .join(latest_system, latest_system.c.version_id == KnowledgeSourceVersion.id)
                    .where(
                        KnowledgeSource.allowlisted.is_(True),
                        KnowledgeSourceVersion.status == "published",
                        KnowledgeSourceSection.embedding.is_not(None),
                    )
                    .order_by(KnowledgeSourceSection.embedding.cosine_distance(query_vector))
                    .limit(20)
                )
            ).all()
            vector.extend(
                SearchCandidate(
                    kind="vector",
                    chunk_id=section.id,
                    source_kind="system",
                    title=title,
                    section_path=section.section_path,
                    snippet=_snippet(section.content, terms),
                    score=1.0,
                    knowledge_source_version_id=version_id,
                )
                for section, title, version_id in system_vectors
            )
        except Exception as exc:
            vector_status = "degraded"
            vector_error_code = getattr(exc, "code", "embedding_unavailable")
            vector = []

    return RetrievalResult(
        evidence=rrf_merge(vector, lexical, limit=limit),
        vector_status=vector_status,
        vector_error_code=vector_error_code,
    )


def _lexical_terms(value: str) -> str:
    """Keep a deterministic, bounded query string for PostgreSQL FTS."""

    return " ".join(tokenize(value))[:1000]


def _tsquery(terms: str) -> object:
    """Build an OR query from the already-sanitized lexical tokens."""

    safe = terms.replace("'", "''")
    return func.to_tsquery("simple", safe.replace(" ", " | "))


def _latest_system_versions() -> Subquery:
    """Select one latest published allowlisted version per source."""

    return (
        select(
            KnowledgeSourceVersion.id.label("version_id"),
            KnowledgeSourceVersion.source_id.label("source_id"),
        )
        .join(KnowledgeSource, KnowledgeSource.id == KnowledgeSourceVersion.source_id)
        .where(
            KnowledgeSourceVersion.status == "published",
            KnowledgeSource.allowlisted.is_(True),
        )
        .distinct(KnowledgeSourceVersion.source_id)
        .order_by(
            KnowledgeSourceVersion.source_id,
            KnowledgeSourceVersion.published_at.desc(),
            KnowledgeSourceVersion.id.desc(),
        )
        .subquery()
    )


def _snippet(content: str, terms: str) -> str:
    compact = " ".join(content.split())
    if len(compact) <= 200:
        return compact
    lowered = compact.casefold()
    positions = [
        lowered.find(term.casefold())
        for term in terms.split()
        if lowered.find(term.casefold()) >= 0
    ]
    center = min(positions) if positions else 0
    start = max(0, min(center - 60, len(compact) - 200))
    return compact[start : start + 200]
