"""Production alert evaluation and webhook delivery."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import (
    AlertDelivery,
    AsyncJob,
    DataDeletionRequest,
    InterviewTurn,
)

ALERT_CODES = (
    "ready_failed",
    "dead_letter",
    "scoring_failed",
    "deletion_failed",
    "worker_heartbeat_stale",
)


@dataclass(frozen=True, slots=True)
class AlertObservation:
    """One actionable alert state with no business content."""

    code: str
    severity: str
    observed_count: int
    message: str


def worker_heartbeat_observation(
    health_file: Path,
    *,
    max_age_seconds: int,
    now: float | None = None,
) -> AlertObservation | None:
    """Return an alert when the Worker health file is absent or stale."""

    current = time.time() if now is None else now
    if not health_file.is_file():
        return AlertObservation(
            code="worker_heartbeat_stale",
            severity="critical",
            observed_count=1,
            message="Worker health file is missing",
        )
    age = max(0.0, current - health_file.stat().st_mtime)
    if age <= max_age_seconds:
        return None
    return AlertObservation(
        code="worker_heartbeat_stale",
        severity="critical",
        observed_count=1,
        message=f"Worker heartbeat is stale ({int(age)}s)",
    )


async def database_observations(session: AsyncSession) -> list[AlertObservation]:
    """Evaluate database-backed alert categories."""

    observations: list[AlertObservation] = []
    dead_letter = int(
        (
            await session.execute(
                select(func.count(AsyncJob.id)).where(AsyncJob.state == "dead_letter")
            )
        ).scalar_one()
    )
    if dead_letter:
        observations.append(
            AlertObservation(
                code="dead_letter",
                severity="critical",
                observed_count=dead_letter,
                message=f"{dead_letter} async jobs are in dead_letter",
            )
        )
    scoring_failed = int(
        (
            await session.execute(
                select(func.count(InterviewTurn.id)).where(InterviewTurn.state == "scoring_failed")
            )
        ).scalar_one()
    )
    if scoring_failed:
        observations.append(
            AlertObservation(
                code="scoring_failed",
                severity="critical",
                observed_count=scoring_failed,
                message=f"{scoring_failed} interview turns failed scoring",
            )
        )
    deletion_failed = int(
        (
            await session.execute(
                select(func.count(DataDeletionRequest.id)).where(
                    DataDeletionRequest.state == "failed"
                )
            )
        ).scalar_one()
    )
    if deletion_failed:
        observations.append(
            AlertObservation(
                code="deletion_failed",
                severity="critical",
                observed_count=deletion_failed,
                message=f"{deletion_failed} deletion requests failed",
            )
        )
    return observations


async def readiness_observation(
    *,
    api_base_url: str,
    request_timeout: float,
    client: httpx.AsyncClient | None = None,
) -> AlertObservation | None:
    """Treat an unreachable or degraded readiness endpoint as an alert."""

    owned_client = client is None
    resolved_client = client or httpx.AsyncClient(timeout=request_timeout)
    try:
        response = await resolved_client.get(f"{api_base_url.rstrip('/')}/health/ready")
        if response.status_code < 300:
            return None
        status = response.status_code
    except httpx.HTTPError:
        status = 0
    finally:
        if owned_client:
            await resolved_client.aclose()
    return AlertObservation(
        code="ready_failed",
        severity="critical",
        observed_count=1,
        message=f"Readiness failed (HTTP {status})",
    )


def _payload(observation: AlertObservation, *, environment: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "alert_code": observation.code,
        "severity": observation.severity,
        "environment": environment,
        "observed_count": observation.observed_count,
        "message": observation.message,
        "observed_at": datetime.now(UTC).isoformat(),
    }


async def deliver_alerts(
    *,
    session: AsyncSession,
    settings: Settings,
    observations: list[AlertObservation],
    client: httpx.AsyncClient | None = None,
) -> list[AlertDelivery]:
    """Send one webhook per observation and persist every attempt."""

    if not observations:
        return []
    if settings.alert_webhook_url is None:
        raise ValueError("alert_webhook_url is not configured")
    headers = {"Content-Type": "application/json"}
    if settings.alert_webhook_token is not None:
        headers["Authorization"] = f"Bearer {settings.alert_webhook_token.get_secret_value()}"
    owned_client = client is None
    resolved_client = client or httpx.AsyncClient(timeout=settings.alert_http_timeout_seconds)
    deliveries: list[AlertDelivery] = []
    try:
        for observation in observations:
            status: int | None = None
            error_detail: str | None = None
            delivered = False
            try:
                response = await resolved_client.post(
                    settings.alert_webhook_url,
                    json=_payload(observation, environment=settings.app_env),
                    headers=headers,
                )
                status = response.status_code
                delivered = 200 <= status < 300
                if not delivered:
                    error_detail = f"webhook returned HTTP {status}"
            except httpx.HTTPError as exc:
                error_detail = f"webhook transport error: {type(exc).__name__}"
            delivery = AlertDelivery(
                alert_code=observation.code,
                severity=observation.severity,
                observed_count=observation.observed_count,
                message=observation.message,
                status="delivered" if delivered else "failed",
                http_status=status,
                error_detail=error_detail,
            )
            session.add(delivery)
            deliveries.append(delivery)
            await session.commit()
    finally:
        if owned_client:
            await resolved_client.aclose()
    return deliveries


async def evaluate_alerts(
    *,
    session: AsyncSession,
    settings: Settings,
    api_base_url: str,
    now: float | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[AlertDelivery]:
    """Evaluate all five alert categories and deliver actionable ones."""

    observations = await database_observations(session)
    ready = await readiness_observation(
        api_base_url=api_base_url,
        request_timeout=settings.alert_http_timeout_seconds,
        client=client,
    )
    if ready is not None:
        observations.append(ready)
    heartbeat = worker_heartbeat_observation(
        Path(settings.worker_health_file),
        max_age_seconds=settings.alert_worker_heartbeat_max_age_seconds,
        now=now,
    )
    if heartbeat is not None:
        observations.append(heartbeat)
    return await deliver_alerts(
        session=session,
        settings=settings,
        observations=observations,
        client=client,
    )


async def clear_alerts(session: AsyncSession) -> None:
    """Clear delivery evidence in isolated test environments only."""

    await session.execute(text("DELETE FROM alert_deliveries"))
    await session.commit()


__all__ = [
    "ALERT_CODES",
    "AlertObservation",
    "database_observations",
    "deliver_alerts",
    "evaluate_alerts",
    "readiness_observation",
    "worker_heartbeat_observation",
]
