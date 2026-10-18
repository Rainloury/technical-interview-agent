"""API skeleton, health, request context, and error envelope tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from app.config import Settings
from app.errors import AppError, install_exception_handlers
from app.health import router
from app.main import create_app
from app.observability import install_request_context
from fastapi import FastAPI
from fastapi.testclient import TestClient


class ReadyState:
    """Minimal state used to exercise readiness through its observable contract."""

    def __init__(self, session_factory: object, redis: object) -> None:
        self.session_factory = session_factory
        self.redis = redis


class FakeSession:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def __aenter__(self) -> "FakeSession":
        if self.fail:
            raise RuntimeError("down")
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, _statement: object) -> None:
        return None


class FakeRedis:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def ping(self) -> bool:
        if self.fail:
            raise ConnectionError("down")
        return True


def test_live_endpoint_returns_request_and_server_headers() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health/live", headers={"X-Request-ID": "req_test"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"] == "req_test"
    assert "X-Server-Time" in response.headers


def test_request_id_is_generated_when_missing() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/ping")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req_")


def test_application_refuses_incomplete_production_configuration() -> None:
    settings = Settings(app_env="production")

    with pytest.raises(ValueError, match="missing deployed configuration"):
        create_app(settings)


def test_unknown_route_envelope_has_request_id() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/missing")

    assert response.status_code == 404
    assert response.headers["X-Request-ID"].startswith("req_")


def test_app_error_uses_stable_envelope() -> None:
    app = FastAPI()
    install_request_context(app)
    install_exception_handlers(app)

    @app.get("/failure")
    async def failure() -> None:
        raise AppError(
            status_code=409,
            code="feedback_locked",
            message="反馈尚未解锁",
            details={"field": "feedback"},
        )

    with TestClient(app) as client:
        response = client.get("/failure")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "feedback_locked",
            "message": "反馈尚未解锁",
            "retryable": False,
            "request_id": response.headers["X-Request-ID"],
            "details": {"field": "feedback"},
        }
    }


def test_validation_error_does_not_echo_input() -> None:
    app = FastAPI()
    install_request_context(app)
    install_exception_handlers(app)

    @app.get("/needs-number")
    async def needs_number(value: int) -> dict[str, int]:
        return {"value": value}

    with TestClient(app) as client:
        response = client.get("/needs-number", params={"value": "secret@example.com"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert "secret@example.com" not in response.text


@pytest.mark.parametrize(
    ("postgres_fails", "redis_fails", "expected_status", "expected"),
    [
        (False, False, 200, {"postgres": "ok", "redis": "ok"}),
        (True, False, 503, {"postgres": "failed", "redis": "ok"}),
        (False, True, 503, {"postgres": "ok", "redis": "failed"}),
        (True, True, 503, {"postgres": "failed", "redis": "failed"}),
    ],
)
def test_readiness_reports_each_dependency(
    postgres_fails: bool,
    redis_fails: bool,
    expected_status: int,
    expected: dict[str, str],
) -> None:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.session_factory = lambda: FakeSession(postgres_fails)
        app.state.redis = FakeRedis(redis_fails)
        yield

    app = FastAPI(lifespan=lifespan)
    install_request_context(app)
    app.include_router(router)

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == expected_status
    assert response.json()["checks"] == expected
    assert response.json()["status"] == ("ok" if expected_status == 200 else "degraded")
