"""请求作用域的共享资源依赖。"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.dependencies.state import app_state
from app.rag.ollama import OllamaEmbeddingClient
from app.storage import ObjectStorage


def get_settings(request: Request) -> Settings:
    """返回应用启动时解析的配置。"""

    return app_state(request).settings


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """返回应用级会话工厂,供流式响应按需开短会话。"""

    return app_state(request).session_factory


def get_resume_storage(request: Request) -> ObjectStorage:
    """返回私有对象存储实现。"""

    return app_state(request).resume_storage


def get_embedding_client(request: Request) -> OllamaEmbeddingClient | None:
    """返回可选的 embedding 客户端。"""

    return app_state(request).embedding_client


SettingsDependency = Annotated[Settings, Depends(get_settings)]
SessionFactoryDependency = Annotated[
    async_sessionmaker[AsyncSession],
    Depends(get_session_factory),
]
StorageDependency = Annotated[ObjectStorage, Depends(get_resume_storage)]
EmbeddingClientDependency = Annotated[
    OllamaEmbeddingClient | None,
    Depends(get_embedding_client),
]
