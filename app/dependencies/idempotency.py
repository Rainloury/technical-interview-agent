"""幂等键依赖。"""

from typing import Annotated

from fastapi import Depends, Header

from app.errors import AppError


def require_idempotency_key(
    value: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    """变更操作需要一个有界的不透明幂等键。"""

    if value is None or not value.strip():
        raise AppError(
            status_code=400,
            code="idempotency_key_required",
            message="缺少 Idempotency-Key",
        )
    normalized = value.strip()
    if len(normalized) > 200:
        raise AppError(
            status_code=400,
            code="invalid_request",
            message="Idempotency-Key 过长",
        )
    return normalized


IdempotencyKeyDependency = Annotated[str, Depends(require_idempotency_key)]
