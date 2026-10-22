"""Validate production configuration without printing secret values."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from app.config import Settings
from pydantic import SecretStr, ValidationError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate deployment configuration and emit a redacted report."
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Repository-external production env file; defaults to process environment.",
    )
    return parser


def _present(value: object | None) -> bool:
    if value is None:
        return False
    if isinstance(value, SecretStr):
        return bool(value.get_secret_value().strip())
    return bool(str(value).strip())


def _report(settings: Settings, env_file: Path | None) -> dict[str, object]:
    settings.validate_deployment()
    app_hosts = sorted(
        {urlsplit(origin).hostname or "invalid" for origin in settings.app_allowed_origins}
    )
    return {
        "status": "PASS",
        "source": str(env_file) if env_file is not None else "process environment",
        "app_env": settings.app_env,
        "debug": settings.app_debug,
        "storage": settings.resume_storage_backend,
        "database_scheme": urlsplit(settings.database_url).scheme,
        "redis_scheme": urlsplit(settings.redis_url).scheme,
        "llm_provider": settings.llm_provider,
        "llm_base_endpoint_configured": bool(settings.llm_base_url),
        "smtp_host": settings.smtp_host,
        "smtp_port": settings.smtp_port,
        "smtp_security": settings.smtp_security,
        "secure_cookie": settings.cookie_secure,
        "app_origin_hosts": app_hosts,
        "csrf_origin_hosts": sorted(
            {urlsplit(origin).hostname or "invalid" for origin in settings.csrf_allowed_origins}
        ),
        "password_reset_https": urlsplit(settings.password_reset_base_url).scheme == "https",
        "data_encryption_key_valid": True,
        "ops_metrics_token_valid": True,
        "alert_webhook_configured": bool(settings.alert_webhook_url),
        "alert_token_configured": settings.alert_webhook_token is not None,
        "worker_concurrency": settings.worker_concurrency,
        "worker_max_runtime_seconds": settings.worker_max_runtime_seconds,
        "worker_idle_seconds": settings.worker_idle_seconds,
        "worker_heartbeat_interval_seconds": settings.worker_heartbeat_interval_seconds,
        "worker_shutdown_grace_seconds": settings.worker_shutdown_grace_seconds,
        "secret_presence": {
            "llm_api_key": _present(settings.llm_api_key),
            "smtp_password": _present(settings.smtp_password),
            "oss_access_key_id": _present(settings.oss_access_key_id),
            "oss_access_key_secret": _present(settings.oss_access_key_secret),
            "data_encryption_key": _present(settings.data_encryption_key),
            "ops_metrics_token": _present(settings.ops_metrics_token),
            "alert_webhook_token": _present(settings.alert_webhook_token),
        },
    }


def main() -> int:
    args = _parser().parse_args()
    try:
        settings = Settings(_env_file=args.env_file)
        report = _report(settings, args.env_file)
    except ValidationError:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "reason": "configuration values have invalid types or formats",
                },
                ensure_ascii=False,
            )
        )
        return 1
    except ValueError as exc:
        print(
            json.dumps(
                {"status": "FAIL", "reason": str(exc)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
