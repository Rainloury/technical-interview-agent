"""Authenticated privacy request and deletion-status endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.api.dependencies import (
    AuthDependency,
    DeletionStatusAuthDependency,
    IdempotencyKeyDependency,
    SessionDependency,
    verify_write_security,
)
from app.schemas.privacy import DataDeletionAccepted, DataDeletionStatus
from app.services.privacy import (
    get_deletion_status,
    latest_deletion_status,
    request_data_deletion,
)

router = APIRouter(tags=["privacy"])


@router.delete(
    "/me/data",
    response_model=DataDeletionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_my_data(
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    idempotency_key: IdempotencyKeyDependency,
) -> DataDeletionAccepted:
    """Tombstone the user's business data and enqueue private cleanup."""

    verify_write_security(request, auth)
    return await request_data_deletion(
        session,
        auth.user,
        idempotency_key=idempotency_key,
        settings=request.app.state.settings,
    )


@router.get("/me/data-deletion", response_model=DataDeletionStatus | None)
async def read_latest_deletion(
    auth: DeletionStatusAuthDependency,
    session: SessionDependency,
) -> DataDeletionStatus | None:
    """Return the latest request status without exposing resource identifiers."""

    return await latest_deletion_status(session, auth.user)


@router.get("/me/data-deletion/{request_id}", response_model=DataDeletionStatus)
async def read_deletion(
    request_id: uuid.UUID,
    auth: DeletionStatusAuthDependency,
    session: SessionDependency,
) -> DataDeletionStatus:
    """Return one owner-scoped deletion status."""

    return await get_deletion_status(session, auth.user, request_id)
