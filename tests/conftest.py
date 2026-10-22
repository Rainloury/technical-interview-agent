"""Shared test configuration and transactional database fixtures."""

import base64
import os
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.config import Settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import Interview, QaRequest, ResumeTask, User
from app.db.session import create_engine, create_session_factory
from app.main import create_app
from app.security import hash_password
from app.storage import LocalPrivateStorage
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip integration tests unless the environment explicitly enables them."""

    if os.getenv("RUN_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_INTEGRATION=1 to run integration tests")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Return isolated settings for the test process."""

    return Settings(
        app_env="test",
        _env_file=None,
        app_allowed_origins=["https://testserver"],
        csrf_allowed_origins=["https://testserver"],
        data_encryption_key=base64.urlsafe_b64encode(os.urandom(32)).decode(),
        resume_storage_dir=str(tmp_path / "resume-files"),
    )


@pytest.fixture
async def db_session(settings: Settings) -> AsyncIterator[AsyncSession]:
    """Provide a schema isolated from other tests and stale rows."""

    schema_name = f"test_{uuid.uuid4().hex}"
    setup_engine = create_async_engine(settings.database_url)
    async with setup_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await setup_engine.dispose()
    engine = create_async_engine(
        settings.database_url,
        connect_args={"server_settings": {"search_path": f"{schema_name},pg_catalog,public"}},
    )
    factory = create_session_factory(engine)
    try:
        async with engine.begin() as connection:
            schema_metadata = MetaData()
            for table in Base.metadata.sorted_tables:
                table.to_metadata(schema_metadata, schema=schema_name)
            await connection.run_sync(schema_metadata.create_all)

        async with engine.connect() as connection:
            transaction = await connection.begin()
            async with factory(
                bind=connection,
                join_transaction_mode="create_savepoint",
            ) as session:
                yield session
            await transaction.rollback()
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        await engine.dispose()


class TestRedis:
    """Small deterministic Redis surface used by authentication tests."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        del key, seconds
        return True

    async def aclose(self) -> None:
        return None


@dataclass(frozen=True, slots=True)
class AppHarness:
    """Application client and a writer connected to its disposable schema."""

    app: FastAPI
    client: TestClient
    session_factory: async_sessionmaker[AsyncSession]
    write_engine: AsyncEngine


@pytest.fixture
async def app_client(
    settings: Settings,
) -> AsyncIterator[AppHarness]:
    """Run API requests against a committed, disposable database schema."""

    schema_name = f"test_{uuid.uuid4().hex}"
    bootstrap_engine = create_async_engine(settings.database_url)
    async with bootstrap_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await bootstrap_engine.dispose()
    setup_engine = create_async_engine(
        settings.database_url,
        connect_args={"server_settings": {"search_path": f"{schema_name},pg_catalog,public"}},
    )
    async with setup_engine.begin() as connection:
        schema_metadata = MetaData()
        for table in Base.metadata.sorted_tables:
            table.to_metadata(schema_metadata, schema=schema_name)
        await connection.run_sync(schema_metadata.create_all)
    await setup_engine.dispose()
    redis = TestRedis()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(
            settings.database_url,
            connect_args={"server_settings": {"search_path": f"{schema_name},pg_catalog,public"}},
        )
        app.state.settings = settings
        app.state.session_factory = create_session_factory(engine)
        app.state.redis = redis
        app.state.resume_storage = LocalPrivateStorage(settings.resume_storage_dir)
        try:
            yield
        finally:
            await engine.dispose()

    app = create_app(settings)
    app.router.lifespan_context = lifespan
    write_engine = create_async_engine(
        settings.database_url,
        connect_args={"server_settings": {"search_path": f"{schema_name},pg_catalog,public"}},
    )
    write_factory = create_session_factory(write_engine)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            yield AppHarness(
                app=app,
                client=client,
                session_factory=write_factory,
                write_engine=write_engine,
            )
    finally:
        await write_engine.dispose()
        cleanup_engine = create_engine(settings)
        async with cleanup_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        await cleanup_engine.dispose()


@pytest.fixture
def create_user() -> Callable[..., User]:
    """Build a password-authenticated account for API tests."""

    def factory(
        email: str,
        *,
        password: str = "correct horse battery staple",  # noqa: S107
        display_name: str | None = "示例用户",
        role: str = "user",
    ) -> User:
        return User(
            email_normalized=email,
            password_hash=hash_password(password),
            display_name=display_name,
            role=role,
        )

    return factory


@pytest.fixture
def create_activity() -> Callable[..., tuple[ResumeTask, QaRequest, Interview]]:
    """Create owner-scoped records used by dashboard and history tests."""

    def factory(user: User, *, suffix: str, day: int) -> tuple[ResumeTask, QaRequest, Interview]:
        timestamp = datetime(2026, 10, day, 8, tzinfo=UTC)
        task = ResumeTask(
            owner_user_id=user.id,
            state="completed",
            created_at=timestamp,
            completed_at=timestamp,
            expires_at=timestamp + timedelta(days=90),
        )
        request = QaRequest(
            owner_user_id=user.id,
            question_text=f"问题 {suffix}",
            state="completed",
            model_name="test-model",
            prompt_version="v1",
            created_at=timestamp,
            completed_at=timestamp,
            expires_at=timestamp + timedelta(days=90),
        )
        interview = Interview(
            owner_user_id=user.id,
            direction="backend",
            difficulty_profile={},
            topic_keys={},
            state="completed",
            total_token_budget=1000,
            blueprint_version="v1",
            scoring_version="v1",
            created_at=timestamp,
            ended_at=timestamp,
            expires_at=timestamp + timedelta(days=90),
        )
        return task, request, interview

    return factory
