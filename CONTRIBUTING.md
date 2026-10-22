# Contributing

Thanks for helping improve Technical Interview Agent. This repository contains
a Python API and worker, a React web client, PostgreSQL migrations, and agent
evaluation cases.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

Prerequisites:

- Python 3.11 or 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker with Compose
- Node.js 22 and npm

Install the Python dependencies and create a local configuration file:

```bash
uv sync
cp .env.example .env
```

Fill only the values needed for the work you are doing. Never commit `.env`,
credentials, private endpoints, or production data.

For the complete local application stack:

```bash
docker compose -f deploy/local.compose.yaml up --build --detach
```

The web application is then available at `http://127.0.0.1:8080`.

For frontend-only development:

```bash
cd web
npm ci
npm run dev
```

## Making changes

1. Create a focused branch from `main`.
2. Read the relevant design material in [`docs/`](docs/README.md) and the
   repository rules in [`AGENTS.md`](AGENTS.md).
3. Keep changes within one concern and add tests for changed behavior.
4. Do not weaken authentication, privacy isolation, or input validation to make
   a test pass.
5. Update public documentation when behavior, configuration, or deployment
   changes.

New dependencies need a clear justification. Prefer the standard library or an
existing dependency when the implementation remains small and readable.

## Checks

Run the checks relevant to the area you changed:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests evals migrations
uv run pytest -q
```

If PostgreSQL and Redis are available:

```bash
uv run alembic upgrade head
RUN_INTEGRATION=1 uv run pytest -m integration -q
```

Frontend checks:

```bash
cd web
npm run typecheck
npm test -- --run
npm run lint
npm run build
```

Browser E2E requires the local service dependencies:

```bash
cd web
npm run test:e2e
```

## Pull requests

Keep pull requests small enough to review. Describe:

- the problem and the chosen approach;
- user-visible or API behavior changes;
- security and migration implications;
- commands run and their results;
- any remaining risk or follow-up work.

Do not include generated reports, local screenshots, logs containing user data,
or secrets in a pull request.

## Security and conduct

Do not report vulnerabilities in a public issue. Follow
[SECURITY.md](SECURITY.md) instead.

Participation in project spaces is governed by
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

Unless you explicitly state otherwise, contributions submitted to this project
are licensed under the Apache License 2.0, as described in [LICENSE](LICENSE).
