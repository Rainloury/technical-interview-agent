"""Validated application configuration."""

from __future__ import annotations

import base64
import binascii
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    def __init__(self, **values: Any) -> None:
        env_file = values.pop("_env_file", ".env")
        super().__init__(_env_file=env_file, **values)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "technical-interview-agent"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_debug: bool = False
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    app_allowed_origins: list[str] = Field(default_factory=lambda: ["http://127.0.0.1:3001"])

    database_url: str = "postgresql+asyncpg://interview:interview@127.0.0.1:55432/interview"
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=5, ge=0)
    database_pool_timeout_seconds: float = Field(default=5, gt=0)
    database_echo: bool = False

    redis_url: str = "redis://127.0.0.1:56379/0"
    redis_socket_timeout_seconds: float = Field(default=2, gt=0)

    session_cookie_name: str = "interview_session"
    csrf_cookie_name: str = "interview_csrf"
    cookie_secure: bool = True
    auth_rate_limit_per_minute: int = Field(default=10, ge=1)
    session_ttl_seconds: int = Field(default=604800, gt=0)
    password_reset_ttl_seconds: int = Field(default=1800, gt=0)
    csrf_allowed_origins: list[str] = Field(default_factory=lambda: ["http://127.0.0.1:3001"])
    data_encryption_key: SecretStr | None = None

    llm_provider: Literal["openai", "anthropic", "deepseek", "local"] = "deepseek"
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None
    llm_fast_model: str = ""
    llm_default_model: str = ""
    llm_reasoning_model: str = ""
    llm_connect_timeout_seconds: float = Field(default=10, gt=0)
    llm_request_timeout_seconds: float = Field(default=60, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_max_output_tokens: int = Field(default=8192, ge=1)
    prompt_dir: str = Field(default_factory=lambda: str(PROJECT_ROOT / "app" / "prompts"))
    tool_result_max_chars: int = Field(default=2000, ge=1)
    tool_result_dir: str = "/private/tmp/technical-interview-agent-tool-results"
    tool_result_ttl_seconds: int = Field(default=3600, ge=1)

    ollama_base_url: str | None = None
    ollama_embedding_model: str = "mxbai-embed-large:latest"
    ollama_embedding_dimensions: int = Field(default=1024, gt=0)
    ollama_connect_timeout_seconds: float = Field(default=5, gt=0)
    ollama_request_timeout_seconds: float = Field(default=30, gt=0)
    ollama_max_retries: int = Field(default=2, ge=0, le=5)
    document_max_bytes: int = Field(default=10_485_760, ge=1)
    document_max_characters: int = Field(default=200_000, ge=1)
    document_chunk_size: int = Field(default=800, ge=100)
    document_chunk_overlap: int = Field(default=100, ge=0)
    rag_embedding_batch_size: int = Field(default=16, ge=1, le=128)

    resume_storage_dir: str = "/private/tmp/technical-interview-agent-resume-files"
    resume_storage_backend: Literal["local", "oss"] = "local"
    oss_endpoint: str | None = None
    oss_bucket: str | None = None
    oss_access_key_id: SecretStr | None = None
    oss_access_key_secret: SecretStr | None = None
    oss_prefix: str = "resumes/"
    resume_max_bytes: int = Field(default=10_485_760, ge=1)
    resume_max_pages: int = Field(default=10, ge=1)
    resume_max_docx_characters: int = Field(default=40_000, ge=1)
    worker_lease_seconds: int = Field(default=60, ge=1)
    worker_max_attempts: int = Field(default=3, ge=1, le=10)
    worker_retry_base_seconds: int = Field(default=5, ge=1)
    worker_retry_max_seconds: int = Field(default=300, ge=1)
    worker_concurrency: int = Field(default=1, ge=1, le=32)
    worker_max_runtime_seconds: int = Field(default=86_400, ge=1)
    worker_idle_seconds: float = Field(default=1.0, gt=0)
    worker_heartbeat_interval_seconds: float = Field(default=10.0, gt=0)
    worker_shutdown_grace_seconds: float = Field(default=30.0, gt=0)
    worker_health_file: str = "/var/run/technical-interview-agent/worker-health.json"
    ops_metrics_token: SecretStr | None = None
    alert_webhook_url: str | None = None
    alert_webhook_token: SecretStr | None = None
    alert_worker_heartbeat_max_age_seconds: int = Field(default=90, ge=30)
    alert_http_timeout_seconds: float = Field(default=5, gt=0)

    smtp_host: str | None = None
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_security: Literal["starttls", "ssl", "none"] = "ssl"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: str | None = None
    mail_local_reset_file: str = "/private/tmp/technical-interview-agent-password-reset.json"
    password_reset_base_url: str = "http://127.0.0.1:3001/reset-password"  # noqa: S105

    @field_validator("app_allowed_origins", "csrf_allowed_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        if not origins:
            raise ValueError("at least one origin is required")
        if any(not origin.startswith(("http://", "https://")) for origin in origins):
            raise ValueError("origins must use http or https")
        return origins

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_base_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        base_url = value.strip().rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("ollama_base_url must use http or https")
        return base_url

    @field_validator("ollama_embedding_model")
    @classmethod
    def validate_ollama_embedding_model(cls, value: str) -> str:
        model = value.strip()
        if not model:
            raise ValueError("ollama_embedding_model must not be blank")
        return model

    @model_validator(mode="after")
    def validate_document_chunk_limits(self) -> Settings:
        if self.document_chunk_overlap >= self.document_chunk_size:
            raise ValueError("document_chunk_overlap must be smaller than document_chunk_size")
        return self

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("database_url must use postgresql+asyncpg")
        return value

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://")):
            raise ValueError("redis_url must use redis or rediss")
        return value

    @field_validator("prompt_dir")
    @classmethod
    def resolve_prompt_dir(cls, value: str) -> str:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path.resolve())

    @field_validator("oss_endpoint")
    @classmethod
    def validate_oss_endpoint(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        endpoint = value.strip()
        if not endpoint.startswith(("https://", "http://")):
            raise ValueError("oss_endpoint must use http or https")
        return endpoint.rstrip("/")

    @field_validator("oss_access_key_id", "oss_access_key_secret")
    @classmethod
    def validate_oss_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            return None
        return value

    @field_validator("oss_prefix")
    @classmethod
    def validate_oss_prefix(cls, value: str) -> str:
        prefix = value.strip().lstrip("/")
        if ".." in Path(prefix).parts:
            raise ValueError("oss_prefix must not escape the bucket root")
        return prefix

    @field_validator("alert_webhook_url")
    @classmethod
    def validate_alert_webhook_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        endpoint = value.strip()
        if not endpoint.startswith(("https://", "http://")):
            raise ValueError("alert_webhook_url must use http or https")
        return endpoint

    def validate_deployment(self) -> None:
        """Reject missing or development-only dependencies when starting a deployment."""
        if self.app_env not in {"staging", "production"}:
            return

        if self.llm_provider == "local":
            raise ValueError("staging/production must not use LLM_PROVIDER=local")

        required = {
            "DATA_ENCRYPTION_KEY": self.data_encryption_key,
            "LLM_API_KEY": self.llm_api_key,
            "LLM_FAST_MODEL": self.llm_fast_model,
            "LLM_DEFAULT_MODEL": self.llm_default_model,
            "LLM_REASONING_MODEL": self.llm_reasoning_model,
            "OLLAMA_BASE_URL": self.ollama_base_url,
            "SMTP_HOST": self.smtp_host,
            "SMTP_USERNAME": self.smtp_username,
            "SMTP_PASSWORD": self.smtp_password,
            "SMTP_FROM_EMAIL": self.smtp_from_email,
            "OPS_METRICS_TOKEN": self.ops_metrics_token,
            "ALERT_WEBHOOK_URL": self.alert_webhook_url,
        }
        if self.resume_storage_backend == "oss":
            required.update(
                {
                    "OSS_ENDPOINT": self.oss_endpoint,
                    "OSS_BUCKET": self.oss_bucket,
                    "OSS_ACCESS_KEY_ID": self.oss_access_key_id,
                    "OSS_ACCESS_KEY_SECRET": self.oss_access_key_secret,
                }
            )
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"missing deployed configuration: {', '.join(missing)}")

        if self.resume_storage_backend != "oss":
            raise ValueError("staging/production require RESUME_STORAGE_BACKEND=oss")
        if not self.cookie_secure:
            raise ValueError("staging/production require COOKIE_SECURE=true")
        if urlsplit(self.password_reset_base_url).scheme != "https":
            raise ValueError("staging/production require an https PASSWORD_RESET_BASE_URL")
        if any(
            urlsplit(origin).scheme != "https"
            for origin in (*self.app_allowed_origins, *self.csrf_allowed_origins)
        ):
            raise ValueError(
                "APP_ALLOWED_ORIGINS and CSRF_ALLOWED_ORIGINS must use https in staging/production"
            )
        if self.ops_metrics_token is None or len(self.ops_metrics_token.get_secret_value()) < 32:
            raise ValueError("OPS_METRICS_TOKEN must be at least 32 characters")
        assert self.data_encryption_key is not None
        encoded_key = self.data_encryption_key.get_secret_value()
        try:
            decoded_key = base64.urlsafe_b64decode(encoded_key + "=" * (-len(encoded_key) % 4))
        except (ValueError, binascii.Error) as exc:
            raise ValueError("DATA_ENCRYPTION_KEY must be a 32-byte URL-safe Base64 key") from exc
        if len(decoded_key) != 32:
            raise ValueError("DATA_ENCRYPTION_KEY must be a 32-byte URL-safe Base64 key")
        if self.alert_webhook_token is not None and not (
            self.alert_webhook_token.get_secret_value().strip()
        ):
            raise ValueError("ALERT_WEBHOOK_TOKEN must not be blank when configured")
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if any(
            (urlsplit(origin).hostname or "").lower() in local_hosts
            for origin in (*self.app_allowed_origins, *self.csrf_allowed_origins)
        ):
            raise ValueError("staging/production must not allow localhost origins")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings object."""

    return Settings()
