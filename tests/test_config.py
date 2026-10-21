"""Configuration validation tests."""

import base64
import os
from pathlib import Path

import pytest
from app.config import Settings
from app.prompts.loader import PromptLoader
from pydantic import ValidationError


def test_rag_defaults_are_explicit() -> None:
    settings = Settings(app_env="test", _env_file=None)

    assert settings.ollama_embedding_model == "bge-m3"
    assert settings.ollama_embedding_dimensions == 1024
    assert settings.document_max_bytes == 10_485_760
    assert settings.document_max_characters == 200_000
    assert settings.document_chunk_size == 800
    assert settings.document_chunk_overlap == 100
    assert settings.rag_embedding_batch_size == 16


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ollama_base_url", "ftp://ollama:11434"),
        ("ollama_embedding_dimensions", 0),
        ("document_chunk_overlap", 800),
        ("rag_embedding_batch_size", 0),
    ],
)
def test_rag_settings_reject_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: value})


def test_settings_accept_supported_dependencies() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@db:5432/name",
        redis_url="rediss://cache:6379/0",
        app_allowed_origins=["https://example.com"],
    )

    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url.startswith("rediss://")
    assert settings.database_pool_size > 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_url", "postgresql://u:p@db/name"),
        ("redis_url", "http://cache:6379/0"),
        ("app_allowed_origins", ["ftp://example.com"]),
        ("csrf_allowed_origins", []),
        ("app_port", 0),
    ],
)
def test_settings_reject_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: value})


def test_sensitive_keys_are_secret() -> None:
    settings = Settings(
        llm_api_key="sk-private",
        smtp_password="smtp-private",
        oss_access_key_secret="oss-private",
    )

    assert "sk-private" not in repr(settings)
    assert "smtp-private" not in repr(settings)
    assert "oss-private" not in repr(settings)


def test_directmail_and_oss_settings_are_validated() -> None:
    settings = Settings(
        smtp_host="smtpdm.aliyun.com",
        smtp_port=465,
        smtp_security="ssl",
        resume_storage_backend="oss",
        oss_endpoint="https://oss-cn-hangzhou.aliyuncs.com/",
        oss_bucket="interview-private",
        oss_access_key_id="key",
        oss_access_key_secret="secret",
        oss_prefix="/resumes/",
    )

    assert settings.smtp_port == 465
    assert settings.smtp_security == "ssl"
    assert settings.oss_endpoint == "https://oss-cn-hangzhou.aliyuncs.com"
    assert settings.oss_prefix == "resumes/"


def test_oss_prefix_cannot_escape_bucket_root() -> None:
    with pytest.raises(ValidationError):
        Settings(oss_prefix="../private")


def _production_settings() -> Settings:
    return Settings(
        app_env="production",
        app_allowed_origins=["https://app.example.com"],
        csrf_allowed_origins=["https://app.example.com"],
        cookie_secure=True,
        data_encryption_key=base64.urlsafe_b64encode(os.urandom(32)).decode(),
        llm_api_key="sk-production",
        llm_fast_model="fast-model",
        llm_default_model="default-model",
        llm_reasoning_model="reasoning-model",
        smtp_host="smtpdm.aliyun.com",
        smtp_username="no-reply@example.com",
        smtp_password="smtp-production",
        smtp_from_email="no-reply@example.com",
        resume_storage_backend="oss",
        oss_endpoint="https://oss-cn-hangzhou.aliyuncs.com",
        oss_bucket="interview-private",
        oss_access_key_id="oss-key",
        oss_access_key_secret="oss-secret",
        password_reset_base_url="https://app.example.com/reset-password",
        ops_metrics_token="ops-production-token-32-characters-min",
        alert_webhook_url="https://alerts.example.com/hooks/technical-interview-agent",
        alert_webhook_token="alert-production-token",
        ollama_base_url="http://ollama.internal:11434",
    )


def test_production_configuration_is_complete_and_safe() -> None:
    settings = _production_settings()
    settings.validate_deployment()

    assert settings.app_env == "production"
    assert settings.resume_storage_backend == "oss"
    assert settings.cookie_secure is True


def test_development_settings_do_not_require_deployment_dependencies() -> None:
    settings = Settings(app_env="development")

    settings.validate_deployment()


def test_settings_can_disable_dotenv_loading(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("APP_ENV=production\n", encoding="utf-8")

    settings = Settings(_env_file=dotenv)
    explicit = Settings(app_env="test", _env_file=dotenv)
    process_only = Settings(_env_file=None)

    assert settings.app_env == "production"
    assert explicit.app_env == "test"
    assert process_only.app_env == "development"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("resume_storage_backend", "local", "RESUME_STORAGE_BACKEND=oss"),
        ("cookie_secure", False, "COOKIE_SECURE=true"),
        (
            "password_reset_base_url",
            "http://app.example.com/reset-password",
            "https PASSWORD_RESET_BASE_URL",
        ),
        (
            "app_allowed_origins",
            ["https://localhost:3001"],
            "must not allow localhost",
        ),
        (
            "csrf_allowed_origins",
            ["https://127.0.0.1:3001"],
            "must not allow localhost",
        ),
        ("smtp_host", None, "missing deployed configuration: SMTP_HOST"),
        ("llm_api_key", None, "missing deployed configuration: LLM_API_KEY"),
        ("ollama_base_url", None, "missing deployed configuration: OLLAMA_BASE_URL"),
        ("alert_webhook_url", None, "missing deployed configuration: ALERT_WEBHOOK_URL"),
    ],
)
def test_production_configuration_rejects_unsafe_or_missing_values(
    field: str,
    value: object,
    message: str,
) -> None:
    settings = _production_settings().model_copy(update={field: value})

    with pytest.raises(ValueError, match=message):
        settings.validate_deployment()


def test_production_configuration_rejects_local_llm_provider() -> None:
    settings = _production_settings().model_copy(update={"llm_provider": "local"})

    with pytest.raises(ValueError, match="LLM_PROVIDER=local"):
        settings.validate_deployment()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "data_encryption_key",
            "not-base64",
            "DATA_ENCRYPTION_KEY must be a 32-byte URL-safe Base64 key",
        ),
        (
            "data_encryption_key",
            base64.urlsafe_b64encode(b"short").decode(),
            "DATA_ENCRYPTION_KEY must be a 32-byte URL-safe Base64 key",
        ),
        (
            "ops_metrics_token",
            None,
            "missing deployed configuration: OPS_METRICS_TOKEN",
        ),
        (
            "ops_metrics_token",
            "too-short",
            "OPS_METRICS_TOKEN must be at least 32 characters",
        ),
        (
            "alert_webhook_token",
            "",
            "ALERT_WEBHOOK_TOKEN must not be blank when configured",
        ),
        (
            "app_allowed_origins",
            ["http://app.example.com"],
            "APP_ALLOWED_ORIGINS and CSRF_ALLOWED_ORIGINS must use https in staging/production",
        ),
        (
            "csrf_allowed_origins",
            ["http://app.example.com"],
            "APP_ALLOWED_ORIGINS and CSRF_ALLOWED_ORIGINS must use https in staging/production",
        ),
    ],
)
def test_production_configuration_rejects_weak_secrets_and_insecure_origins(
    field: str,
    value: object,
    message: str,
) -> None:
    values = _production_settings().model_dump()
    values[field] = value
    settings = Settings(**values, _env_file=None)

    with pytest.raises(ValueError, match=message):
        settings.validate_deployment()


def test_relative_prompt_dir_is_independent_of_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    settings = Settings(prompt_dir="app/prompts")
    prompt = PromptLoader(settings.prompt_dir).load("resume_analysis")

    expected = Path(__file__).resolve().parents[1] / "app" / "prompts"
    assert Path(settings.prompt_dir) == expected
    assert prompt.name == "resume_analysis"
