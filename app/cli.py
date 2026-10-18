"""Small command-line entry point for local operation."""

import argparse
import asyncio

import uvicorn

from app.config import Settings, get_settings


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

    settings = Settings(_env_file=None)
    await WorkerRunner(settings=settings).run()


def main() -> None:
    """Run the API or production Worker from the same executable."""

    parser = argparse.ArgumentParser(description="Technical interview agent")
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("command", nargs="?", choices=("api", "worker"), default="api")
    args = parser.parse_args()
    if args.command == "worker":
        if args.reload:
            parser.error("--reload is only supported for the api command")
        asyncio.run(_run_worker())
        return
    _run_api(reload=args.reload)


if __name__ == "__main__":
    main()
