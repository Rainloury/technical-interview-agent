"""HTTP multipart 上传的有界读取。"""

from __future__ import annotations

from fastapi import UploadFile

from app.errors import AppError


async def read_bounded_upload(file: UploadFile, max_bytes: int) -> bytes:
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
