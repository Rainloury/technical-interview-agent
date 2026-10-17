"""PostgreSQL-backed job leasing with fencing checks."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AsyncJob


async def lease_next_job(
    session: AsyncSession,
    *,
    worker_id: str,
    lease_seconds: int = 60,
    allowed_job_ids: tuple[uuid.UUID, ...] | None = None,
) -> AsyncJob | None:
    """Lease one due job and increment its fencing token atomically.

    ``allowed_job_ids`` is an optional partitioning/filter hook for callers
    that must remain isolated from unrelated queued work, such as tests or a
    future sharded worker pool.
    """

    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    if allowed_job_ids is not None and not allowed_job_ids:
        return None
    stmt = (
        select(AsyncJob)
        .where(
            AsyncJob.state.in_(("queued", "leased")),
            AsyncJob.next_run_at <= text("statement_timestamp()"),
            (AsyncJob.lease_until.is_(None))
            | (AsyncJob.lease_until < text("statement_timestamp()")),
        )
        .order_by(AsyncJob.next_run_at, AsyncJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if allowed_job_ids is not None:
        stmt = stmt.where(AsyncJob.id.in_(allowed_job_ids))
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None
    await session.execute(
        update(AsyncJob)
        .where(AsyncJob.id == job.id)
        .values(
            state="leased",
            lease_owner=worker_id,
            fencing_token=AsyncJob.fencing_token + 1,
            lease_until=text(f"statement_timestamp() + interval '{int(lease_seconds)} seconds'"),
            attempt_count=AsyncJob.attempt_count + 1,
            updated_at=text("statement_timestamp()"),
        )
    )
    await session.refresh(job)
    return job


async def finish_job(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    fencing_token: int,
    state: str,
    error_code: str | None = None,
    error_detail: str | None = None,
    next_run_at: datetime | None = None,
) -> bool:
    """Finish a job only when the caller still owns the current lease."""

    values: dict[str, Any] = {
        "state": "queued" if state == "failed" and next_run_at is not None else state,
        "lease_owner": None,
        "lease_until": None,
        "updated_at": text("statement_timestamp()"),
    }
    if error_code is not None:
        values["error_code"] = error_code
    if error_detail is not None:
        values["error_detail"] = error_detail
    if next_run_at is not None:
        values["next_run_at"] = next_run_at
    result = await session.execute(
        update(AsyncJob)
        .where(
            AsyncJob.id == job_id,
            AsyncJob.lease_owner == worker_id,
            AsyncJob.fencing_token == fencing_token,
        )
        .values(**values)
    )
    return bool(result.rowcount)


async def renew_job_lease(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    fencing_token: int,
    lease_seconds: int = 60,
) -> bool:
    """Extend a lease only for the current owner and fencing token."""

    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    result = await session.execute(
        update(AsyncJob)
        .where(
            AsyncJob.id == job_id,
            AsyncJob.lease_owner == worker_id,
            AsyncJob.fencing_token == fencing_token,
            AsyncJob.state == "leased",
        )
        .values(
            lease_until=text(f"statement_timestamp() + interval '{int(lease_seconds)} seconds'"),
            updated_at=text("statement_timestamp()"),
        )
    )
    return bool(result.rowcount)
