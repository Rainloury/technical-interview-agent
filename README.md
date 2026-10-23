# Technical Interview Agent

English | [Chinese](README.zh-CN.md) | [Live site](https://it.rainstone.top)

A self-hostable technical interview platform with a bounded answer agent,
private document retrieval, and an async worker.

> Current status: **v0.1.0 is officially released and live at
> [it.rainstone.top](https://it.rainstone.top)**. The latest `main` branch is in
> post-release iteration and includes shared-document administration and mobile
> release work added after the `v0.1.0` tag. See
> [`docs/README.md`](docs/README.md), [`CHANGELOG.md`](CHANGELOG.md), and
> [`docs/release-runbook.md`](docs/release-runbook.md) for release facts,
> verification evidence, and the next rollout boundary.

The application provides:

- account registration, session management, password reset, and CSRF-protected
  writes;
- resume upload, question answering, simulated interviews, reports, and review;
- private internal-document libraries with PDF, DOCX, TXT, and Markdown upload;
- administrator-managed shared documents visible to every signed-in account;
- per-file asynchronous indexing and owner-isolated hybrid retrieval;
- pgvector cosine search plus PostgreSQL lexical BM25-style ranking, fused with
  reciprocal rank fusion (RRF);
- automatic use of the current user's ready documents during question answering,
  with no document selector;
- deterministic fallback to lexical retrieval when the embedding service is
  unavailable;
- `mxbai-embed-large:latest` as the default 1024-dimension embedding model;
- a React web client and Docker Compose deployment.

The service is built for technical interview workflows. It is not a general
chatbot, and it does not automatically perform external write actions.

Sessions use the server-side `interview_session` cookie (`HttpOnly`) and a
separate `interview_csrf` verifier for `X-CSRF-Token` checks. Database records
store only the hashes in `auth_sessions.csrf_token_hash`. Paginated history
endpoints return `{items, next_cursor}`.

## Architecture

```text
Browser
  |
  v
Nginx web container
  |-- static React application
  `-- /api and /health proxy
          |
          +--> FastAPI API
          |      |-- PostgreSQL + pgvector
          |      |-- Redis
          |      |-- model provider
          |      `-- Ollama embeddings
          |
          `--> async worker
                 |-- document extraction and indexing
                 |-- interview processing
                 |-- password-reset delivery
                 `-- retention cleanup
```

The Python application follows `api -> agent -> tools -> llm`. PostgreSQL is the
source of truth for sessions and asynchronous jobs. See
[`docs/adr/`](docs/adr/README.md) for architecture decisions and
[`docs/technical-design.md`](docs/technical-design.md) for the current design.

## Quick start

### Full local stack

Prerequisites: Docker with Compose.

```bash
cp .env.example .env
docker compose -f deploy/local.compose.yaml up --build --detach
```

Open `http://127.0.0.1:8080`. The stack runs PostgreSQL, Redis, migrations, the
API, the worker, and the web server in containers. It does not publish the host
PostgreSQL, Redis, or API ports.

Embeddings require an independently deployed Ollama service. For local use, set
`OLLAMA_BASE_URL` in `.env` to an endpoint your containers can reach, for
example `http://host.docker.internal:11434`. The default embedding model is
`mxbai-embed-large:latest` with 1024 dimensions. If Ollama is unavailable,
question answering falls back to lexical retrieval; document indexing retries
and then fails cleanly rather than writing partial vectors.

### Python and web development

Prerequisites:

- Python 3.11 or 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 22 and npm
- PostgreSQL with pgvector and Redis, or Docker for those services

```bash
uv sync
cp .env.example .env
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

In another terminal:

```bash
cd web
npm ci
npm run dev
```

The API listens on `http://127.0.0.1:8000` and the Vite client on
`http://127.0.0.1:3001` by default. Set `VITE_API_BASE_URL` to override the API
origin used by the frontend.

## Configuration

Configuration is loaded through `app/config.py` and documented by
`.env.example`. Copy the example to `.env` and supply values locally. Never
commit `.env`, credentials, private keys, or production endpoints.

The most important settings are:

| Area | Settings |
| --- | --- |
| Runtime | `APP_ENV`, `APP_DEBUG`, `APP_ALLOWED_ORIGINS` |
| PostgreSQL | `DATABASE_URL` |
| Redis | `REDIS_URL` |
| Sessions | `SESSION_COOKIE_NAME`, `CSRF_COOKIE_NAME`, `COOKIE_SECURE`, `DATA_ENCRYPTION_KEY` |
| Model provider | `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, model tier names |
| Embeddings | `OLLAMA_BASE_URL`, `OLLAMA_EMBEDDING_MODEL`, `OLLAMA_EMBEDDING_DIMENSIONS` |
| Resume storage | `RESUME_STORAGE_BACKEND`, local path or S3-compatible OSS settings |
| Email | `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, credentials, sender |
| Worker | `WORKER_CONCURRENCY`, runtime and shutdown limits |

Staging and production startup validates required security-sensitive settings
and fails fast when they are incomplete. The production template is
[`deploy/production.env.example`](deploy/production.env.example).

## Document retrieval

Authenticated users can upload one or more PDF, DOCX, TXT, or Markdown files of
up to 10 MB each. The batch endpoint creates an independent document and index
job per file. The worker extracts, chunks, embeds, and stores each file
separately.

The public document API is owner-scoped:

```text
POST   /api/v1/documents
POST   /api/v1/documents/batch
GET    /api/v1/documents
GET    /api/v1/documents/{document_id}
DELETE /api/v1/documents/{document_id}
```

Administrators can also manage shared documents. Every signed-in user can read shared
documents, but only administrators can upload or delete them:

```text
POST   /api/v1/shared-documents
POST   /api/v1/shared-documents/batch
GET    /api/v1/shared-documents
GET    /api/v1/shared-documents/{document_id}
DELETE /api/v1/shared-documents/{document_id}
```

Personal documents remain owner-scoped even for administrators. A shared document is
retrieved by every signed-in account after it becomes ready.

Only documents in the `ready` state participate in retrieval. Deleting a
document removes it from future retrieval immediately; historical evidence is
marked `source_deleted`, and stored content is cleaned up asynchronously.

Retrieval takes the top 20 cosine candidates and top 20 lexical candidates,
fuses them with equal-weight RRF (`k=60`), and returns the top 5. The full
contract is in [`docs/api-contract.md`](docs/api-contract.md), and the rationale
is in
[ADR-0009](docs/adr/0009-hybrid-rag-for-private-documents.md).

## Development

Backend checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests evals migrations
uv run pytest -q
```

Integration tests require PostgreSQL and Redis:

```bash
RUN_INTEGRATION=1 uv run pytest -m integration -q
```

Frontend checks:

```bash
cd web
npm run typecheck
npm test -- --run
npm run lint
npm run build
npm run test:e2e
```

Deterministic evaluation and provider-dependent evaluation are separate:

```bash
uv run python -m evals.run
uv run python -m evals.provider_behavior
```

The second command performs real provider calls and requires a configured
`LLM_API_KEY`. Provider evaluations are opt-in.

Project rules and agent constraints are in [`AGENTS.md`](AGENTS.md). Public
documentation starts at [`docs/README.md`](docs/README.md).

## Deployment

Production uses separate `migrate`, `api`, `worker`, and `web` services. Only
the Nginx entrypoint is exposed. API and worker images run as non-root users
with a read-only root filesystem where supported.

The deployment and rollback procedure is in
[`docs/release-runbook.md`](docs/release-runbook.md). The production Compose
definition is
[`deploy/production.compose.yaml`](deploy/production.compose.yaml).

Build images with:

```bash
docker build --pull -t technical-interview-agent:v0.1.0 .
docker build --pull -t technical-interview-agent-web:v0.1.0 web/
```

Use immutable image digests for production rollouts. Keep the production
environment file outside the repository and inject it through your secret
manager or deployment platform.

## Android

The Capacitor Android shell is in `web/android` and targets the same-origin
production site at `https://it.rainstone.top`. See
[`docs/android-release.md`](docs/android-release.md) for local
builds, release signing, GitHub Actions and Google Play Console steps.

## iOS

The native `WKWebView` wrapper is in `ios/` and keeps the existing same-origin
authentication, CSRF, upload and SSE behavior. See
[`docs/superpowers/specs/ios-release-design.md`](docs/superpowers/specs/ios-release-design.md)
for the design and [`docs/superpowers/plans/ios-release.md`](docs/superpowers/plans/ios-release.md)
for remaining work; build steps are in [`docs/ios-release.md`](docs/ios-release.md).

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request.
Participation is governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

- Support and issue guidance: [`SUPPORT.md`](SUPPORT.md)
- Security reports: [`SECURITY.md`](SECURITY.md)
- Release history: [`CHANGELOG.md`](CHANGELOG.md)
- Dependency and font notices: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)

## License

Copyright 2026 Rainloury.

Licensed under the [Apache License, Version 2.0](LICENSE).
