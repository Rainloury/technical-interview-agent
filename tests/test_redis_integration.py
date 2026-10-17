"""Redis readiness integration test."""

import pytest
from app.config import Settings
from app.redis import create_redis

pytestmark = pytest.mark.integration


async def test_redis_ping(settings: Settings) -> None:
    redis = create_redis(settings)
    try:
        assert await redis.ping() is True
    finally:
        await redis.aclose()
