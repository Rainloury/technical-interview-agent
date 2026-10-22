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
        "PIP_DEFAULT_TIMEOUT=120",
        "PIP_RETRIES=8",
        "PIP_INDEX_URL",
        "uv pip sync",
        "requirements.txt",
        "uv pip install --system --no-cache --no-deps .",
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
        "web:",
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


def test_production_nginx_is_the_public_entry_and_serves_spa() -> None:
    compose = _read("deploy/production.compose.yaml")
    nginx = _read("web/nginx.conf")

    for fragment in (
        "location /api/",
        "proxy_pass $api_upstream$request_uri;",
        "resolver 127.0.0.11 valid=10s ipv6=off;",
        "proxy_buffering off;",
        "proxy_set_header X-Forwarded-Proto $scheme;",
        "try_files $uri $uri/ /index.html;",
        "location = /healthz",
    ):
        assert fragment in nginx

    for fragment in (
        "web:",
        "${WEB_IMAGE_REPOSITORY:?set WEB_IMAGE_REPOSITORY}",
        "${WEB_BIND_ADDRESS:-0.0.0.0}:${WEB_PORT:-8080}:8080",
    ):
        assert fragment in compose

    assert "listen 8080;" in nginx
    assert "listen 80;" not in nginx
    assert "ports:" in compose.split("  web:", 1)[1].split("  postgres:", 1)[0]
    assert "api:\n    <<: *application" in compose
    assert 'expose:\n      - "8000"' in compose
    assert "API_BIND_ADDRESS" not in compose
    web = compose.split("  web:", 1)[1].split("  postgres:", 1)[0]
    assert "cap_add:" not in web
    assert "http://127.0.0.1:8080/healthz" in web


def test_web_image_builds_static_assets_and_ships_nginx_healthcheck() -> None:
    dockerfile = _read("web/Dockerfile")

    for fragment in (
        "FROM node:22-alpine AS build",
        "npm ci",
        "npm run build",
        "COPY index.html tokens.css tsconfig.json vite.config.ts ./",
        "FROM nginx:1.27-alpine",
        "COPY nginx.conf /etc/nginx/conf.d/default.conf",
        "COPY nginx-main.conf /etc/nginx/nginx.conf",
        "COPY --from=build /workspace/dist /usr/share/nginx/html",
        "USER nginx",
        "EXPOSE 8080",
        "http://127.0.0.1:8080/healthz",
    ):
        assert fragment in dockerfile

    assert "EXPOSE 80\n" not in dockerfile


def test_production_compose_requires_explicit_image_and_secret_env() -> None:
    compose = _read("deploy/production.compose.yaml")

    for variable in (
        "IMAGE_REPOSITORY",
        "WEB_IMAGE_REPOSITORY",
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
        "WEB_BIND_ADDRESS",
        "WEB_PORT",
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

    for ignored in (".git", ".env", ".venv", "tests", "docs", "scripts", "deploy"):
        assert ignored in dockerignore.splitlines()
    assert "app" not in dockerignore.splitlines()
    assert "migrations" not in dockerignore.splitlines()


def test_local_compose_builds_application_image_once_for_all_backend_roles() -> None:
    compose = _read("deploy/local.compose.yaml")
    backend_services = compose.split("  postgres:", 1)[1].split("  web:", 1)[0]

    assert backend_services.count("dockerfile: Dockerfile") == 1
    assert backend_services.count("image: technical-interview-agent-api:local") >= 3
    assert "args:\n        PIP_INDEX_URL:" in backend_services
    assert backend_services.count("args:") == 1
    assert "name: technical-interview-agent-local" in compose
    assert "127.0.0.1:8080:8080" in compose
    web = compose.split("  web:", 1)[1].split("volumes:", 1)[0]
    assert "http://127.0.0.1:8080/healthz" in web


def test_local_compose_initializes_shared_storage_before_application() -> None:
    compose = _read("deploy/local.compose.yaml")
    storage_init = compose.split("  storage-init:", 1)[1].split("  migrate:", 1)[0]

    assert 'user: "0:0"' in storage_init
    assert "chown -R 10001:10001 /var/lib/technical-interview-agent" in storage_init
    for service in ("migrate:", "api:", "worker:"):
        section = compose.split(f"  {service}", 1)[1]
        assert "storage-init:\n        condition: service_completed_successfully" in section


def test_synology_compose_is_self_contained_for_npm_reverse_proxy() -> None:
    compose = _read("deploy/synology.compose.yaml")
    env_example = _read("deploy/synology.env.example")

    for fragment in (
        "name: technical-interview-agent-synology",
        "WEB_BIND_ADDRESS:-192.168.50.66",
        "WEB_PORT:-8080}:8080",
        "APP_ENV: development",
        "APP_ALLOWED_ORIGINS: ${APP_ALLOWED_ORIGINS:",
        "CSRF_ALLOWED_ORIGINS: ${CSRF_ALLOWED_ORIGINS:",
        "COOKIE_SECURE: ${COOKIE_SECURE:-true}",
        "PASSWORD_RESET_BASE_URL: ${PASSWORD_RESET_BASE_URL:",
        "RESUME_STORAGE_BACKEND: local",
        "OLLAMA_BASE_URL: ${OLLAMA_BASE_URL:-http://host.docker.internal:11434}",
        "OLLAMA_EMBEDDING_MODEL: ${OLLAMA_EMBEDDING_MODEL:-",
        "OLLAMA_EMBEDDING_DIMENSIONS: ${OLLAMA_EMBEDDING_DIMENSIONS:-",
        'APP_ALLOWED_ORIGINS: ${APP_ALLOWED_ORIGINS:-["https://it.rainstone.top"]}',
        'CSRF_ALLOWED_ORIGINS: ${CSRF_ALLOWED_ORIGINS:-["https://it.rainstone.top"]}',
        "PASSWORD_RESET_BASE_URL: ${PASSWORD_RESET_BASE_URL:-https://it.rainstone.top/reset-password}",
        "storage-init:",
        'user: "0:0"',
        "chown -R 10001:10001",
        "read_only: true",
        "no-new-privileges:true",
        "cap_drop:",
        "/health/ready",
        "worker-health.json",
        "http://127.0.0.1:8080/healthz",
    ):
        assert fragment in compose

    assert "APP_ENV: production" not in compose
    assert "192.168.50.66:100" not in compose
    assert "${PRODUCTION_ENV_FILE" not in compose
    assert "env_file:" not in compose
    assert 'ports:\n      - "${API' not in compose
    assert 'ports:\n      - "${REDIS' not in compose
    assert 'ports:\n      - "${POSTGRES' not in compose
    assert "external: true" not in compose
    assert compose.count("build:") == 2

    for variable in (
        "POSTGRES_PASSWORD",
        "DATA_ENCRYPTION_KEY",
        "LLM_API_KEY",
        "APP_ALLOWED_ORIGINS",
        "CSRF_ALLOWED_ORIGINS",
        "COOKIE_SECURE",
        "PASSWORD_RESET_BASE_URL",
        "OLLAMA_BASE_URL",
        "OLLAMA_EMBEDDING_MODEL",
        "OLLAMA_EMBEDDING_DIMENSIONS",
        "WEB_BIND_ADDRESS",
        "WEB_PORT",
    ):
        assert f"{variable}=" in env_example
    assert "APP_ENV=" not in env_example
    assert 'APP_ALLOWED_ORIGINS=["https://it.rainstone.top"]' in env_example
    assert 'CSRF_ALLOWED_ORIGINS=["https://it.rainstone.top"]' in env_example
    assert "PASSWORD_RESET_BASE_URL=https://it.rainstone.top/reset-password" in env_example


def test_deployment_uses_pgvector_and_ollama_configuration() -> None:
    production = _read("deploy/production.compose.yaml")
    local = _read("deploy/local.compose.yaml")
    env_example = _read(".env.example")
    production_env_example = _read("deploy/production.env.example")

    assert "pgvector/pgvector:pg16" in production
    assert "pgvector/pgvector:pg16" in local
    assert "OLLAMA_BASE_URL" in env_example
    assert "WORKER_HEARTBEAT_INTERVAL_SECONDS=10" in env_example
    assert "WORKER_HEARTBEAT_INTERVAL_SECONDS=10" in production_env_example
    assert "OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest" in env_example
    assert "OLLAMA_EMBEDDING_DIMENSIONS=1024" in env_example


def test_ci_initializes_pgvector_extension() -> None:
    workflow = _read(".github/workflows/ci.yml")
    migration = _read("migrations/versions/7f3a9c2d1b40_add_user_rag.py")

    assert "pgvector/pgvector:pg16" in workflow
    assert workflow.count("image: pgvector/pgvector:pg16") == 2
    assert "uv run alembic downgrade base" in workflow
    assert "uv run alembic upgrade head" in workflow
    assert "uv run alembic check" in workflow
    assert "CREATE EXTENSION IF NOT EXISTS vector" in migration
    assert 'postgresql_using="hnsw"' in migration
    assert 'postgresql_ops={"embedding": "vector_cosine_ops"}' in migration


def test_playwright_wrapper_handles_empty_focused_args() -> None:
    wrapper = _read("web/scripts/playwright-with-servers.mjs")

    assert "PLAYWRIGHT_ARGS" in wrapper
    assert "?? []" in wrapper
