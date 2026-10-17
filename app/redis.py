"""Redis client lifecycle."""

from typing import cast

from redis.asyncio import Redis

from app.config import Settings


def create_redis(settings: Settings) -> Redis:
    """Create the shared asynchronous Redis client."""

    return cast(
        Redis,
        Redis.from_url(
            settings.redis_url,
            socket_timeout=settings.redis_socket_timeout_seconds,
            decode_responses=True,
        ),
    )
