"""Shared test configuration and transactional database fixtures."""

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from app.config import Settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import create_engine, create_session_factory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip integration tests unless the environment explicitly enables them."""

    if os.getenv("RUN_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_INTEGRATION=1 to run integration tests")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def settings() -> Settings:
    """Return isolated settings for the test process."""

    return Settings(
        app_env="test",
        app_allowed_origins=["http://testserver"],
        csrf_allowed_origins=["http://testserver"],
    )


@pytest.fixture
async def db_session(settings: Settings) -> AsyncIterator[AsyncSession]:
    """Provide a schema isolated from other tests and stale rows."""

    engine = create_engine(settings)
    schema_name = f"test_{uuid.uuid4().hex}"
    factory = create_session_factory(engine)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
            await connection.execute(text(f'SET LOCAL search_path TO "{schema_name}"'))
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                )
            )

        async with engine.connect() as connection:
            transaction = await connection.begin()
            await connection.execute(text(f'SET LOCAL search_path TO "{schema_name}"'))
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
