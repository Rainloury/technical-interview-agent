"""按所有者隔离的简历上传和生命周期端点。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, Response, UploadFile, status

from app.api.dependencies import (
    AuthDependency,
    IdempotencyKeyDependency,
    SessionDependency,
    verify_write_security,
)
from app.errors import AppError
from app.schemas.resume import ResumeAccepted, ResumeTaskView
from app.services.resumes import (
    ResumeUpload,
    delete_resume_source,
    get_resume_task,
    retry_resume_task,
    upload_resume,
)

router = APIRouter(prefix="/resumes", tags=["resumes"])


async def _read_bounded_upload(file: UploadFile, max_bytes: int) -> bytes:
    """分块读取 multipart 文件并在达到限制时立即停止。"""

    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(64 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise AppError(
                status_code=413,
                code="file_too_large",
                message="文件不能超过 10 MB",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", response_model=ResumeAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_resume(
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    idempotency_key: IdempotencyKeyDependency,
    file: Annotated[UploadFile, File()],
    target_role: Annotated[str | None, Form()] = None,
) -> ResumeAccepted:
    """校验并私有存储 PDF 或 DOCX 简历。"""

    del target_role
    verify_write_security(request, auth)
    settings = request.app.state.settings
    content = await _read_bounded_upload(file, settings.resume_max_bytes)
    return await upload_resume(
        session,
        request.app.state.resume_storage,
        auth.user,
        ResumeUpload(
            filename=file.filename or "",
            declared_mime=file.content_type,
            content=content,
        ),
        idempotency_key=idempotency_key,
        settings=settings,
    )


@router.get("/{task_id}", response_model=ResumeTaskView)
async def read_resume(
    task_id: uuid.UUID,
    auth: AuthDependency,
    session: SessionDependency,
) -> ResumeTaskView:
    """返回当前所有者的简历任务。"""

    return await get_resume_task(session, auth.user, task_id)


@router.post(
    "/{task_id}/retry",
    response_model=ResumeAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_resume(
    task_id: uuid.UUID,
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    idempotency_key: IdempotencyKeyDependency,
) -> ResumeAccepted:
    """从失败任务仍为私有的源创建新任务。"""

    verify_write_security(request, auth)
    return await retry_resume_task(
        session,
        request.app.state.resume_storage,
        auth.user,
        task_id,
        idempotency_key=idempotency_key,
        settings=request.app.state.settings,
    )


@router.delete("/{task_id}/source", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    task_id: uuid.UUID,
    request: Request,
    auth: AuthDependency,
    session: SessionDependency,
    idempotency_key: IdempotencyKeyDependency,
) -> Response:
    """将源文件标记为墓碑并仅删除该文件。"""

    verify_write_security(request, auth)
    await delete_resume_source(
        session,
        request.app.state.resume_storage,
        auth.user,
        task_id,
        idempotency_key=idempotency_key,
        settings=request.app.state.settings,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
