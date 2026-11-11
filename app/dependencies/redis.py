"""Redis 客户端生命周期与请求依赖。"""

from typing import Annotated, cast

from fastapi import Depends, Request
from redis.asyncio import Redis

from app.config import Settings
from app.dependencies.state import app_state


def create_redis(settings: Settings) -> Redis:
    """创建共享的异步 Redis 客户端。"""

    return cast(
        Redis,
        Redis.from_url(
            settings.redis_url,
            socket_timeout=settings.redis_socket_timeout_seconds,
            decode_responses=True,
        ),
    )


def get_redis(request: Request) -> Redis:
    """返回应用级 Redis 客户端。"""

    return app_state(request).redis


RedisDependency = Annotated[Redis, Depends(get_redis)]
