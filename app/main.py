"""FastAPI application assembly."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.config import Settings, get_settings
from app.db.session import create_engine, create_session_factory
from app.errors import install_exception_handlers
from app.health import router as health_router
from app.logging import configure_logging, get_logger
from app.observability import install_request_context
from app.rag.ollama import OllamaEmbeddingClient
from app.redis import create_redis
from app.storage import create_resume_storage


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the application."""

    resolved = settings or get_settings()
    resolved.validate_deployment()
    configure_logging(resolved.app_log_level)
    logger = get_logger("app.lifecycle")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(resolved)
        redis = create_redis(resolved)
        app.state.settings = resolved
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.redis = redis
        app.state.resume_storage = create_resume_storage(resolved)
        embedding_client = (
            OllamaEmbeddingClient(resolved) if resolved.ollama_base_url is not None else None
        )
        app.state.embedding_client = embedding_client
        logger.info("application starting", environment=resolved.app_env)
        try:
            yield
        finally:
            await redis.aclose()
            if embedding_client is not None:
                await embedding_client.aclose()
            await engine.dispose()
            logger.info("application stopped")

    app = FastAPI(
        title="Technical Interview Agent",
        version="0.1.0",
        debug=resolved.app_debug,
        lifespan=lifespan,
    )
    install_request_context(app)
    install_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.app_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Idempotency-Key",
            "Last-Event-ID",
            "X-CSRF-Token",
            "X-Request-ID",
        ],
        expose_headers=["X-Request-ID", "X-Server-Time"],
    )
    app.include_router(health_router)
    app.include_router(v1_router)
    return app


app = create_app()
