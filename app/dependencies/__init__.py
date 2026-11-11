"""FastAPI 依赖注入统一入口。"""

from app.dependencies.auth import (
    AuthContext,
    AuthDependency,
    DeletionStatusAuthDependency,
    get_auth_context,
    get_deletion_status_auth,
    require_admin,
    verify_write_security,
)
from app.dependencies.db import SessionDependency, get_session
from app.dependencies.idempotency import (
    IdempotencyKeyDependency,
    require_idempotency_key,
)
from app.dependencies.pagination import CursorDependency, parse_cursor
from app.dependencies.redis import RedisDependency, create_redis, get_redis
from app.dependencies.resources import (
    EmbeddingClientDependency,
    SessionFactoryDependency,
    SettingsDependency,
    StorageDependency,
    get_embedding_client,
    get_resume_storage,
    get_session_factory,
    get_settings,
)

__all__ = [
    "AuthContext",
    "AuthDependency",
    "CursorDependency",
    "DeletionStatusAuthDependency",
    "EmbeddingClientDependency",
    "IdempotencyKeyDependency",
    "RedisDependency",
    "SessionDependency",
    "SessionFactoryDependency",
    "SettingsDependency",
    "StorageDependency",
    "create_redis",
    "get_auth_context",
    "get_deletion_status_auth",
    "get_embedding_client",
    "get_redis",
    "get_resume_storage",
    "get_session",
    "get_session_factory",
    "get_settings",
    "parse_cursor",
    "require_admin",
    "require_idempotency_key",
    "verify_write_security",
]
