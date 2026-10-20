"""Small command-line entry point for local operation."""

import argparse
import asyncio
from collections.abc import Sequence

import uvicorn

from app.config import get_settings
from app.db.session import create_engine, create_session_factory


def _run_api(*, reload: bool) -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=reload,
        log_config=None,
    )


async def _run_worker() -> None:
    from app.worker import WorkerRunner

    settings = get_settings()
    await WorkerRunner(settings=settings).run()


async def _run_alerts() -> None:
    from app.alerts import evaluate_alerts

    settings = get_settings()
    if settings.alert_webhook_url is None:
        raise ValueError("ALERT_WEBHOOK_URL is required for alert checks")
    engine = create_engine(settings)
    try:
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            wildcard_host = ".".join(("0", "0", "0", "0"))
            api_host = "127.0.0.1" if settings.app_host == wildcard_host else settings.app_host
            deliveries = await evaluate_alerts(
                session=session,
                settings=settings,
                api_base_url=f"http://{api_host}:{settings.app_port}",
            )
            for delivery in deliveries:
                print(
                    f"{delivery.alert_code}|{delivery.status}|{delivery.http_status}",
                    flush=True,
                )
            if any(delivery.status != "delivered" for delivery in deliveries):
                raise RuntimeError("one or more alert deliveries failed")
    finally:
        await engine.dispose()


def _command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Technical interview agent")
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("api", "worker", "migrate", "alerts"),
        default="api",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run the API or production Worker from the same executable."""

    parser = _command_parser()
    args = parser.parse_args(argv)
    if args.command == "migrate":
        if args.reload:
            parser.error("--reload is only supported for the api command")
        from alembic.config import main as alembic_main

        alembic_main(argv=["upgrade", "head"])
        return
    if args.command == "worker":
        if args.reload:
            parser.error("--reload is only supported for the api command")
        asyncio.run(_run_worker())
        return
    if args.command == "alerts":
        if args.reload:
            parser.error("--reload is only supported for the api command")
        asyncio.run(_run_alerts())
        return
    _run_api(reload=args.reload)


if __name__ == "__main__":
    main()
