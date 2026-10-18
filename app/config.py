"""Validated application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

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

    llm_provider: Literal["openai", "anthropic", "deepseek"] = "deepseek"
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

    resume_storage_dir: str = "/private/tmp/technical-interview-agent-resume-files"
    resume_max_bytes: int = Field(default=10_485_760, ge=1)
    resume_max_pages: int = Field(default=10, ge=1)
    resume_max_docx_characters: int = Field(default=40_000, ge=1)
    worker_lease_seconds: int = Field(default=60, ge=1)
    worker_max_attempts: int = Field(default=3, ge=1, le=10)
    worker_retry_base_seconds: int = Field(default=5, ge=1)
    worker_retry_max_seconds: int = Field(default=300, ge=1)
    ops_metrics_token: SecretStr | None = None

    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: str | None = None
    password_reset_base_url: str = "http://127.0.0.1:3001/reset-password"  # noqa: S105

    @field_validator("app_allowed_origins", "csrf_allowed_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        if not origins:
            raise ValueError("at least one origin is required")
        if any(not origin.startswith(("http://", "https://")) for origin in origins):
            raise ValueError("origins must use http or https")
        return origins

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


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings object."""

    return Settings()
