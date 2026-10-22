"""Owner-scoped private document upload and lifecycle endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile, status

from app.api.dependencies import (
    AuthDependency,
    IdempotencyKeyDependency,
    SessionDependency,
    verify_write_security,
)
from app.errors import AppError
from app.schemas.documents import (
    DocumentAccepted,
    DocumentBatchAccepted,
    DocumentItem,
    DocumentPage,
)
from app.services.documents import (
    DocumentUpload,
    delete_document,
    get_document,
    list_documents,
    upload_document,
    upload_documents,
)

router = APIRouter(prefix="/documents", tags=["documents"])


async def _read_bounded(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(64 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise AppError(status_code=413, code="file_too_large", message="文件不能超过 10 MB")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", response_model=DocumentAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload(
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    idempotency_key: IdempotencyKeyDependency,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
) -> DocumentAccepted:
    verify_write_security(request, auth)
    settings = request.app.state.settings
    content = await _read_bounded(file, settings.document_max_bytes)
    return await upload_document(
        session,
        request.app.state.resume_storage,
        auth.user,
        DocumentUpload(
            filename=file.filename or "",
            declared_mime=file.content_type,
            content=content,
            title=title,
        ),
        idempotency_key=idempotency_key,
        settings=settings,
    )


@router.post("/batch", response_model=DocumentBatchAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_batch(
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    idempotency_key: IdempotencyKeyDependency,
    files: Annotated[list[UploadFile], File()],
) -> DocumentBatchAccepted:
    verify_write_security(request, auth)
    settings = request.app.state.settings
    uploads = []
    for file in files:
        content = await _read_bounded(file, settings.document_max_bytes)
        uploads.append(
            DocumentUpload(
                filename=file.filename or "",
                declared_mime=file.content_type,
                content=content,
                title=None,
            )
        )
    return await upload_documents(
        session,
        request.app.state.resume_storage,
        auth.user,
        uploads,
        idempotency_key=idempotency_key,
        settings=settings,
    )


@router.get("", response_model=DocumentPage)
async def list_all(
    auth: AuthDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> DocumentPage:
    return await list_documents(session, auth.user, limit=limit, cursor=cursor)


@router.get("/{document_id}", response_model=DocumentItem)
async def detail(
    document_id: uuid.UUID,
    auth: AuthDependency,
    session: SessionDependency,
) -> DocumentItem:
    return await get_document(session, auth.user, document_id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(
    document_id: uuid.UUID,
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    idempotency_key: IdempotencyKeyDependency,
) -> Response:
    verify_write_security(request, auth)
    await delete_document(
        session,
        auth.user,
        document_id,
        idempotency_key=idempotency_key,
        settings=request.app.state.settings,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
