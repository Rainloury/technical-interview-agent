"""System knowledge embedding backfill contract tests."""

from __future__ import annotations

import asyncio
import uuid
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app import cli
from app.config import Settings
from app.db.models import (
    KnowledgeSource,
    KnowledgeSourceSection,
    KnowledgeSourceVersion,
    QaEvidence,
    QaRequest,
    User,
)
from app.rag.backfill import BackfillResult, backfill_system_embeddings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


class FakeEmbedding:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[0.1] * 1024 for _ in texts]


async def test_backfill_is_idempotent_and_skips_noncurrent_sources(
    db_session: AsyncSession,
    settings: Settings,
) -> None:
    now = datetime.now(UTC)
    user = User(email_normalized="backfill@example.com", password_hash="x")
    source = KnowledgeSource(
        source_type="official_doc",
        title="Backfill source",
        source_uri="https://docs.example/backfill",
        allowlisted=True,
    )
    db_session.add_all([user, source])
    await db_session.flush()
    old_version = KnowledgeSourceVersion(
        source_id=source.id,
        version_label="v1",
        content_hash=uuid.uuid4().hex,
        published_at=now - timedelta(days=2),
        status="published",
    )
    latest_version = KnowledgeSourceVersion(
        source_id=source.id,
        version_label="v2",
        content_hash=uuid.uuid4().hex,
        published_at=now,
        status="published",
    )
    draft_version = KnowledgeSourceVersion(
        source_id=source.id,
        version_label="draft",
        content_hash=uuid.uuid4().hex,
        published_at=now,
        status="draft",
    )
    db_session.add_all([old_version, latest_version, draft_version])
    await db_session.flush()
    latest_section = KnowledgeSourceSection(
        version_id=latest_version.id,
        section_index=0,
        section_path="正文 / 1",
        content="latest private knowledge",
        search_text="latest private knowledge",
        token_count=3,
    )
    old_section = KnowledgeSourceSection(
        version_id=old_version.id,
        section_index=0,
        section_path="正文 / 1",
        content="old private knowledge",
        search_text="old private knowledge",
        token_count=3,
    )
    draft_section = KnowledgeSourceSection(
        version_id=draft_version.id,
        section_index=0,
        section_path="正文 / 1",
        content="draft private knowledge",
        search_text="draft private knowledge",
        token_count=3,
    )
    db_session.add_all([latest_section, old_section, draft_section])
    await db_session.flush()
    request = QaRequest(
        owner_user_id=user.id,
        question_text="history",
        state="completed",
        model_name="test",
        prompt_version="test",
        expires_at=now + timedelta(days=1),
    )
    db_session.add(request)
    await db_session.flush()
    evidence = QaEvidence(
        qa_request_id=request.id,
        knowledge_source_version_id=latest_version.id,
        source_title="Backfill source",
        section_path="正文 / 1",
        snippet="frozen",
        relevance_score=0.5,
        position={"rank": 1},
    )
    db_session.add(evidence)
    await db_session.commit()

    embedding = FakeEmbedding()
    result = await backfill_system_embeddings(
        db_session,
        embedding_client=embedding,
        settings=settings,
        batch_size=2,
    )

    assert result.processed == 1
    assert result.failed == 0
    assert len(embedding.calls) == 1
    await db_session.refresh(latest_section)
    await db_session.refresh(old_section)
    await db_session.refresh(draft_section)
    assert latest_section.embedding is not None
    assert latest_section.embedding_index_version == "rag-v1"
    assert old_section.embedding is None
    assert draft_section.embedding is None
    frozen = (
        await db_session.execute(select(QaEvidence).where(QaEvidence.id == evidence.id))
    ).scalar_one()
    assert frozen.snippet == "frozen"

    replay = await backfill_system_embeddings(
        db_session,
        embedding_client=embedding,
        settings=settings,
        batch_size=2,
    )
    assert replay.processed == 0
    assert replay.skipped >= 1


def test_cli_rag_backfill_prints_counts_and_fails_on_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeParser:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def add_argument(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def parse_args(self, _argv: object = None) -> Namespace:
            return Namespace(command="rag-backfill", reload=False)

    class FakeEmbedding:
        async def aclose(self) -> None:
            return None

    class FakeEngine:
        async def dispose(self) -> None:
            return None

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    def fake_session_factory() -> FakeSession:
        return FakeSession()

    async def fake_backfill(
        session: object,
        *,
        embedding_client: object,
        settings: Settings,
    ) -> BackfillResult:
        del session, embedding_client, settings
        return BackfillResult(processed=2, skipped=1, failed=0)

    def fake_run(coroutine: Any) -> None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coroutine)
        finally:
            loop.close()

    settings = Settings(
        app_env="test",
        ollama_base_url="http://ollama.test:11434",
        _env_file=None,
    )
    monkeypatch.setattr("app.cli.argparse.ArgumentParser", FakeParser)
    monkeypatch.setattr("app.cli.get_settings", lambda: settings)
    monkeypatch.setattr("app.cli.create_engine", lambda _settings: FakeEngine())
    monkeypatch.setattr("app.cli.create_session_factory", lambda _engine: fake_session_factory)
    monkeypatch.setattr("app.rag.ollama.OllamaEmbeddingClient", lambda _settings: FakeEmbedding())
    monkeypatch.setattr("app.rag.backfill.backfill_system_embeddings", fake_backfill)
    monkeypatch.setattr("app.cli.asyncio.run", fake_run)

    cli.main()

    assert "processed=2 skipped=1 failed=0" in capsys.readouterr().out
