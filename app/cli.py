"""Small command-line entry point for local operation."""

import argparse

import uvicorn

from app.config import get_settings


def main() -> None:
    """Run the API with environment-backed host and port settings."""

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Technical interview agent")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=args.reload,
        log_config=None,
    )


if __name__ == "__main__":
    main()
