"""Small aggregate operational metrics queries for release monitoring."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AsyncJob,
    AuditEvent,
    DataDeletionRequest,
    FollowUpChain,
    InterviewTurn,
)
from app.schemas.dashboard import OperationalMetrics


async def operational_metrics(session: AsyncSession) -> OperationalMetrics:
    """Return bounded aggregate counters, never business content or IDs."""

    jobs_by_state = {
        str(state): int(count)
        for state, count in (
            await session.execute(
                select(AsyncJob.state, func.count(AsyncJob.id)).group_by(AsyncJob.state)
            )
        ).all()
    }
    jobs_by_type = {
        str(job_type): int(count)
        for job_type, count in (
            await session.execute(
                select(AsyncJob.job_type, func.count(AsyncJob.id)).group_by(AsyncJob.job_type)
            )
        ).all()
    }
    termination_reasons = {
        str(reason): int(count)
        for reason, count in (
            await session.execute(
                select(FollowUpChain.termination_reason, func.count(FollowUpChain.id))
                .where(FollowUpChain.termination_reason.is_not(None))
                .group_by(FollowUpChain.termination_reason)
            )
        ).all()
    }
    deletion_states = {
        str(state): int(count)
        for state, count in (
            await session.execute(
                select(DataDeletionRequest.state, func.count(DataDeletionRequest.id)).group_by(
                    DataDeletionRequest.state
                )
            )
        ).all()
    }
    scoring_failed = int(
        (
            await session.execute(
                select(func.count(InterviewTurn.id)).where(InterviewTurn.state == "scoring_failed")
            )
        ).scalar_one()
    )
    expired_audit = int(
        (
            await session.execute(
                select(func.count(AuditEvent.id)).where(AuditEvent.expires_at <= datetime.now(UTC))
            )
        ).scalar_one()
    )
    return OperationalMetrics(
        generated_at=datetime.now(UTC),
        jobs_by_state=jobs_by_state,
        jobs_by_type=jobs_by_type,
        interview_scoring_failed=scoring_failed,
        interview_termination_reasons=termination_reasons,
        deletion_requests_by_state=deletion_states,
        expired_audit_events=expired_audit,
    )
