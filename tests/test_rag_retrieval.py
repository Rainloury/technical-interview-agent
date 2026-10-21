"""Hybrid retrieval ranking and owner isolation tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.db.models import (
    KnowledgeSource,
    KnowledgeSourceSection,
    KnowledgeSourceVersion,
    UserDocument,
    UserDocumentChunk,
)
from app.rag.retrieval import SearchCandidate, hybrid_retrieve, rrf_merge

from tests.conftest import AppHarness

pytestmark = pytest.mark.integration


def _candidate(
    *,
    chunk_id: uuid.UUID,
    title: str,
    source_kind: str = "system",
    kind: str = "vector",
) -> SearchCandidate:
    return SearchCandidate(
        kind=kind,  # type: ignore[arg-type]
        chunk_id=chunk_id,
        source_kind=source_kind,  # type: ignore[arg-type]
        title=title,
        section_path="正文 / 1",
        snippet=f"{title} snippet",
        score=0.9,
    )


def test_rrf_merge_deduplicates_and_limits() -> None:
    shared = uuid.uuid4()
    vector = [_candidate(chunk_id=shared, title="共享")] + [
        _candidate(chunk_id=uuid.uuid4(), title=f"v{index}") for index in range(6)
    ]
    lexical = [_candidate(chunk_id=shared, title="共享", kind="lexical")] + [
        _candidate(chunk_id=uuid.uuid4(), title=f"l{index}", kind="lexical") for index in range(6)
    ]

    merged = rrf_merge(vector, lexical, limit=5)

    assert len(merged) == 5
    assert len({item.chunk_id for item in merged}) == 5
    assert merged[0].chunk_id == shared
    assert merged[0].position["citation_id"] == "evidence-1"


def test_rrf_merge_uses_one_route_when_other_is_empty() -> None:
    candidate = _candidate(chunk_id=uuid.uuid4(), title="only lexical", kind="lexical")
    merged = rrf_merge([], [candidate], limit=5)

    assert len(merged) == 1
    assert merged[0].title == "only lexical"


async def test_hybrid_lexical_retrieval_is_owner_scoped_and_skips_not_ready(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    owner = create_user("retrieval-owner@example.com")
    stranger = create_user("retrieval-stranger@example.com")
    async with app_client.session_factory() as session:
        session.add_all([owner, stranger])
        await session.flush()
        now = datetime.now(UTC)
        owner_doc = UserDocument(
            owner_user_id=owner.id,
            title="Owner notes",
            original_filename="owner.md",
            detected_mime="text/markdown",
            size_bytes=10,
            sha256="a" * 64,
            object_key=f"{owner.id.hex}/owner.md",
            state="ready",
            chunk_count=1,
            retention_expires_at=now + timedelta(days=90),
        )
        stranger_doc = UserDocument(
            owner_user_id=stranger.id,
            title="Stranger notes",
            original_filename="stranger.md",
            detected_mime="text/markdown",
            size_bytes=10,
            sha256="b" * 64,
            object_key=f"{stranger.id.hex}/stranger.md",
            state="ready",
            chunk_count=1,
            retention_expires_at=now + timedelta(days=90),
        )
        pending_doc = UserDocument(
            owner_user_id=owner.id,
            title="Pending notes",
            original_filename="pending.md",
            detected_mime="text/markdown",
            size_bytes=10,
            sha256="c" * 64,
            object_key=f"{owner.id.hex}/pending.md",
            state="uploaded",
            chunk_count=0,
            retention_expires_at=now + timedelta(days=90),
        )
        session.add_all([owner_doc, stranger_doc, pending_doc])
        await session.flush()
        for document, text in (
            (owner_doc, "uniqueowner Redis retry"),
            (stranger_doc, "stranger Redis retry"),
        ):
            session.add(
                UserDocumentChunk(
                    document_id=document.id,
                    owner_user_id=document.owner_user_id,
                    chunk_index=0,
                    section_path="正文 / 1",
                    content=text,
                    content_hash=uuid.uuid4().hex,
                    search_text=text,
                    token_count=3,
                    embedding=[0.0] * 1024,
                )
            )
        source = KnowledgeSource(
            source_type="official_doc",
            title="System retry notes",
            source_uri="https://docs.example/retry",
            allowlisted=True,
        )
        session.add(source)
        await session.flush()
        version = KnowledgeSourceVersion(
            source_id=source.id,
            version_label="v1",
            content_hash=uuid.uuid4().hex,
            published_at=now,
            status="published",
        )
        session.add(version)
        await session.flush()
        section = KnowledgeSourceSection(
            version_id=version.id,
            section_index=0,
            section_path="Retry",
            content="system Redis retry guidance",
            search_text="system Redis retry guidance",
            token_count=4,
        )
        session.add(section)
        await session.commit()

    async with app_client.session_factory() as session:
        result = await hybrid_retrieve(
            session,
            owner_user_id=owner.id,
            question="Redis retry",
            embedding_client=None,
        )

    assert result.vector_status == "disabled"
    assert result.evidence
    assert any(item.title == "Owner notes" for item in result.evidence)
    assert any(item.source_kind == "system" for item in result.evidence)
    assert all(item.title != "Stranger notes" for item in result.evidence)
    assert all(item.title != "Pending notes" for item in result.evidence)
