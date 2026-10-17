"""Liveness and readiness endpoints."""

import asyncio
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.observability import current_server_time

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    """Health response payload."""

    status: Literal["ok", "degraded"]
    server_time: datetime


class ReadinessResponse(HealthResponse):
    """Dependency-level readiness response."""

    checks: dict[str, Literal["ok", "failed"]]


@router.get("/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    """Report process liveness without checking external services."""

    return HealthResponse(status="ok", server_time=datetime.now(UTC))


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"description": "A required dependency is unavailable"}},
)
async def ready(request: Request) -> ReadinessResponse | JSONResponse:
    """Check PostgreSQL and Redis availability."""

    checks: dict[str, Literal["ok", "failed"]] = {}

    async def check_postgres() -> None:
        async with request.app.state.session_factory() as session:
            await session.execute(text("SELECT 1"))

    async def check_redis() -> None:
        await request.app.state.redis.ping()

    for name, check in (("postgres", check_postgres), ("redis", check_redis)):
        try:
            await asyncio.wait_for(check(), timeout=2)
            checks[name] = "ok"
        except Exception:
            checks[name] = "failed"

    status: Literal["ok", "degraded"] = (
        "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    )
    response = ReadinessResponse(
        status=status,
        server_time=current_server_time(),
        checks=checks,
    )
    if status == "degraded":
        return JSONResponse(status_code=503, content=response.model_dump(mode="json"))
    return response
