"""Configuration validation tests."""

from pathlib import Path

import pytest
from app.config import Settings
from app.prompts.loader import PromptLoader
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
