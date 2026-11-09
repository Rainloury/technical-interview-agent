"""需认证的隐私请求和删除状态端点。"""

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
    """将用户的业务数据标记为墓碑并排队私有清理。"""

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
    """返回最新的请求状态而不暴露资源标识符。"""

    return await latest_deletion_status(session, auth.user)


@router.get("/me/data-deletion/{request_id}", response_model=DataDeletionStatus)
async def read_deletion(
    request_id: uuid.UUID,
    auth: DeletionStatusAuthDependency,
    session: SessionDependency,
) -> DataDeletionStatus:
    """返回一个按所有者隔离的删除状态。"""

    return await get_deletion_status(session, auth.user, request_id)
