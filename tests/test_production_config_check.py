"""Contract tests for the redacted production configuration check."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from scripts.check_production_config import main

ROOT = Path(__file__).resolve().parents[1]


def _env_text(*, include_ops_token: bool = True) -> str:
    lines = [
        "APP_ENV=production",
        "APP_DEBUG=false",
        'APP_ALLOWED_ORIGINS=["https://app.example.com"]',
        'CSRF_ALLOWED_ORIGINS=["https://app.example.com"]',
        "COOKIE_SECURE=true",
        "DATABASE_URL=postgresql+asyncpg://user:db-private@db:5432/interview",
        "REDIS_URL=redis://redis:6379/0",
        f"DATA_ENCRYPTION_KEY={base64.urlsafe_b64encode(os.urandom(32)).decode()}",
        "LLM_API_KEY=llm-private",
        "LLM_FAST_MODEL=fast-model",
        "LLM_DEFAULT_MODEL=default-model",
        "LLM_REASONING_MODEL=reasoning-model",
        "OLLAMA_BASE_URL=http://ollama.internal:11434",
        "RESUME_STORAGE_BACKEND=oss",
        "OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com",
        "OSS_BUCKET=interview-private",
        "OSS_ACCESS_KEY_ID=oss-key-private",
        "OSS_ACCESS_KEY_SECRET=oss-secret-private",
        "SMTP_HOST=smtpdm.aliyun.com",
        "SMTP_PORT=465",
        "SMTP_SECURITY=ssl",
        "SMTP_USERNAME=smtp-user-private",
        "SMTP_PASSWORD=smtp-password-private",
        "SMTP_FROM_EMAIL=no-reply@example.com",
        "PASSWORD_RESET_BASE_URL=https://app.example.com/reset-password",
        "ALERT_WEBHOOK_URL=https://alerts.example.com/hooks/interview",
        "ALERT_WEBHOOK_TOKEN=alert-token-private",
    ]
    if include_ops_token:
        lines.append("OPS_METRICS_TOKEN=ops-token-0123456789-0123456789-0123456789")
    return "\n".join(lines) + "\n"


def _run(env_file: Path, capsys: object) -> tuple[int, str, str]:
    import sys

    original_argv = sys.argv
    try:
        sys.argv = [
            "check-production-config",
            "--env-file",
            str(env_file),
        ]
        exit_code = main()
    finally:
        sys.argv = original_argv
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    return exit_code, captured.out, captured.err


def test_production_config_check_emits_only_redacted_facts(
    tmp_path: Path,
    capsys: object,
) -> None:
    env_file = tmp_path / "production.env"
    env_file.write_text(_env_text(), encoding="utf-8")

    exit_code, stdout, stderr = _run(env_file, capsys)

    assert exit_code == 0, stderr
    report = json.loads(stdout)
    assert report["status"] == "PASS"
    assert report["data_encryption_key_valid"] is True
    assert report["ops_metrics_token_valid"] is True
    assert report["app_origin_hosts"] == ["app.example.com"]
    for secret in (
        "db-private",
        "llm-private",
        "oss-key-private",
        "oss-secret-private",
        "smtp-user-private",
        "smtp-password-private",
        "alert-token-private",
        "ops-token-0123456789",
    ):
        assert secret not in stdout
        assert secret not in stderr


def test_production_config_check_fails_on_missing_ops_token(
    tmp_path: Path,
    capsys: object,
) -> None:
    env_file = tmp_path / "production.env"
    env_file.write_text(_env_text(include_ops_token=False), encoding="utf-8")

    exit_code, stdout, _ = _run(env_file, capsys)

    assert exit_code == 1
    report = json.loads(stdout)
    assert report["status"] == "FAIL"
    assert "OPS_METRICS_TOKEN" in report["reason"]
