"""类型化的应用状态视图。"""

from typing import Protocol, cast

from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.rag.ollama import OllamaEmbeddingClient
from app.storage import ObjectStorage


class AppState(Protocol):
    """由应用生命周期写入的共享资源。"""

    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    resume_storage: ObjectStorage
    embedding_client: OllamaEmbeddingClient | None
    redis: Redis


def app_state(request: Request) -> AppState:
    """返回带类型的请求应用状态。"""

    return cast(AppState, request.app.state)
