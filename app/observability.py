"""请求 ID、追踪上下文、结构化访问日志与服务器时间。"""

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
    """返回应用时钟用于 API 诊断。"""

    return datetime.now(UTC)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """附加请求/追踪 ID,记录一次访问事件,并返回服务器时间。"""

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
    """安装请求上下文中间件。"""

    app.add_middleware(RequestContextMiddleware)
