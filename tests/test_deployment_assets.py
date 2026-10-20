"""Production image and Compose deployment contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_production_image_is_locked_non_root_and_uses_uv() -> None:
    dockerfile = _read("Dockerfile")

    for fragment in (
        "FROM python:3.12-slim-bookworm",
        "COPY requirements.txt",
        "COPY pyproject.toml",
        "COPY README.md",
        "pip install --no-cache-dir --requirement requirements.txt",
        "USER app",
        'technical-interview-agent", "api',
        "HEALTHCHECK",
    ):
        assert fragment in dockerfile
    assert "COPY . ." not in dockerfile
    assert "USER root" not in dockerfile


def test_production_compose_separates_migration_api_and_worker() -> None:
    compose = _read("deploy/production.compose.yaml")

    for fragment in (
        "migrate:",
        'command: ["technical-interview-agent", "migrate"]',
        "api:",
        'command: ["technical-interview-agent", "api"]',
        "worker:",
        'command: ["technical-interview-agent", "worker"]',
        "alerts:",
        'command: ["technical-interview-agent", "alerts"]',
        'network_mode: "service:api"',
        "worker-health:/var/run/technical-interview-agent",
        "worker-health:",
        "condition: service_healthy",
        'restart: "no"',
        "stop_grace_period: 35s",
        "/health/ready",
        "worker-health.json",
        "/var/run/technical-interview-agent:size=1m,mode=1777",
        "read_only: true",
        "no-new-privileges:true",
        "cap_drop:",
    ):
        assert fragment in compose


def test_production_compose_requires_explicit_image_and_secret_env() -> None:
    compose = _read("deploy/production.compose.yaml")

    for variable in (
        "IMAGE_REPOSITORY",
        "IMAGE_TAG",
        "PRODUCTION_ENV_FILE",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    ):
        assert f"${{{variable}:?set {variable}}}" in compose


def test_production_compose_variables_template_is_explicit_and_safe() -> None:
    template = _read("deploy/production.compose.env.example")

    for variable in (
        "IMAGE_REPOSITORY",
        "IMAGE_TAG",
        "PRODUCTION_ENV_FILE",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "API_BIND_ADDRESS",
        "API_PORT",
    ):
        assert f"{variable}=" in template
    assert "APP_ENV=" not in template
    assert "LLM_API_KEY=" not in template
    assert "SMTP_PASSWORD=" not in template
    assert "OSS_ACCESS_KEY_SECRET=" not in template


def test_alert_service_uses_api_localhost_and_shared_worker_health_volume() -> None:
    compose = _read("deploy/production.compose.yaml")

    assert 'network_mode: "service:api"' in compose
    assert "api:\n        condition: service_healthy" in compose
    assert "worker-health:/var/run/technical-interview-agent" in compose
    assert "worker-health:/var/run/technical-interview-agent:ro" in compose
    assert "POSTGRES_DB" in compose
    assert "worker-health:" in compose.split("volumes:", 1)[-1]


def test_production_stack_has_explicit_migration_and_readiness_order() -> None:
    compose = _read("deploy/production.compose.yaml")
    assert "migrate:\n        condition: service_completed_successfully" in compose
    assert "worker:\n        condition: service_healthy" in compose


def test_production_compose_uses_isolated_project_name() -> None:
    compose = _read("deploy/production.compose.yaml")
    assert "name: technical-interview-agent-production" in compose
    assert "name: technical-interview-agent\n" not in compose


def test_production_compose_separates_application_and_compose_env_files() -> None:
    compose = _read("deploy/production.compose.yaml")
    template = _read("deploy/production.compose.env.example")

    assert "env_file:\n    - ${PRODUCTION_ENV_FILE:?set PRODUCTION_ENV_FILE}" in compose
    assert "PRODUCTION_ENV_FILE=/secure/path/production.env" in template
    assert "APP_ENV=" not in template
    assert "LLM_API_KEY=" not in template
    assert "SMTP_PASSWORD=" not in template
    assert "OSS_ACCESS_KEY_SECRET=" not in template


def test_docker_context_excludes_secrets_and_nonproduction_assets() -> None:
    dockerignore = _read(".dockerignore")

    for ignored in (".git", ".env", ".venv", "tests", "docs", "scripts"):
        assert ignored in dockerignore.splitlines()
    assert "app" not in dockerignore.splitlines()
    assert "migrations" not in dockerignore.splitlines()
