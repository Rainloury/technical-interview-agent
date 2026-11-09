"""Redis 客户端生命周期。"""

from typing import cast

from redis.asyncio import Redis

from app.config import Settings


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
