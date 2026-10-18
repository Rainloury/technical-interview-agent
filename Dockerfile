# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY pyproject.toml ./
COPY README.md ./
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --requirement requirements.txt \
    && python -m pip install --no-cache-dir --no-deps .

ENV APP_ENV=production \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    WORKER_HEALTH_FILE=/var/run/technical-interview-agent/worker-health.json

RUN mkdir -p /var/run/technical-interview-agent \
    && chown app:app /var/run/technical-interview-agent

USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"]

CMD ["technical-interview-agent", "api"]
