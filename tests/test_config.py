"""Configuration validation tests."""

import pytest
from app.config import Settings
from pydantic import ValidationError


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
    settings = Settings(llm_api_key="sk-private", smtp_password="smtp-private")

    assert "sk-private" not in repr(settings)
    assert "smtp-private" not in repr(settings)
