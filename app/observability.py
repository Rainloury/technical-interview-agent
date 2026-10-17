"""Request IDs, trace context, structured access logs, and server time."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import perf_counter

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.errors import error_payload
from app.logging import get_logger

REQUEST_ID_HEADER = "X-Request-ID"
SERVER_TIME_HEADER = "X-Server-Time"


def current_server_time() -> datetime:
    """Return the application clock for API diagnostics."""

    return datetime.now(UTC)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request/trace IDs, log one access event, and return server time."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or f"req_{uuid.uuid4().hex}"
        trace_id = request.headers.get("traceparent") or uuid.uuid4().hex
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, trace_id=trace_id)
        started = perf_counter()
        logger = get_logger("app.request")
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "unhandled request error",
                method=request.method,
                path=request.url.path,
            )
            response = JSONResponse(
                status_code=500,
                content=error_payload(
                    request_id=request_id,
                    code="internal_error",
                    message="服务暂时不可用",
                ),
            )
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[SERVER_TIME_HEADER] = current_server_time().isoformat()
        logger.info(
            "request completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        structlog.contextvars.clear_contextvars()
        return response


def install_request_context(app: FastAPI) -> None:
    """Install request context middleware."""

    app.add_middleware(RequestContextMiddleware)
