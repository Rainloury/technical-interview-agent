"""Document extraction, normalization, and chunk contract tests."""

from __future__ import annotations

import io

import pytest
from app.config import Settings
from app.errors import AppError
from app.rag.chunking import split_document
from app.rag.extraction import extract_document
from docx import Document
from pypdf import PdfWriter


def _settings(**values: object) -> Settings:
    return Settings(app_env="test", _env_file=None, **values)


def _docx_bytes(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _pdf_bytes(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    page.extract_text = lambda: text  # type: ignore[method-assign]
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("filename", "mime", "content"),
    [
        ("notes.txt", "text/plain", "Redis\n\n  LRU 淘汰  ".encode()),
        ("notes.md", "text/markdown", "# Redis\n\nRedis 使用 LRU 淘汰。".encode()),
        ("notes.docx", None, _docx_bytes("Redis 使用 LRU 淘汰。")),
    ],
)
def test_extract_document_supports_expected_formats(
    filename: str,
    mime: str | None,
    content: bytes,
) -> None:
    extracted = extract_document(
        content,
        filename=filename,
        declared_mime=mime,
        settings=_settings(),
    )

    assert "Redis" in extracted.text
    assert extracted.detected_mime
    assert extracted.text == extracted.text.strip()


def test_empty_pdf_text_is_rejected() -> None:
    with pytest.raises(AppError) as raised:
        extract_document(
            _pdf_bytes("Redis 使用 LRU 淘汰。"),
            filename="notes.pdf",
            declared_mime=None,
            settings=_settings(),
        )

    assert raised.value.code == "text_extraction_unsupported"


@pytest.mark.parametrize(
    ("filename", "mime", "content", "code"),
    [
        ("empty.txt", "text/plain", b"", "invalid_request"),
        ("empty.txt", "text/plain", b"   ", "text_extraction_unsupported"),
        ("notes.exe", "application/octet-stream", b"binary", "unsupported_source"),
    ],
)
def test_extract_document_rejects_empty_and_unsupported_inputs(
    filename: str,
    mime: str | None,
    content: bytes,
    code: str,
) -> None:
    with pytest.raises(AppError) as raised:
        extract_document(
            content,
            filename=filename,
            declared_mime=mime,
            settings=_settings(),
        )

    assert raised.value.code == code


def test_extract_document_rejects_too_much_text() -> None:
    settings = _settings(document_max_characters=10)

    with pytest.raises(AppError) as raised:
        extract_document(
            b"x" * 11,
            filename="large.txt",
            declared_mime="text/plain",
            settings=settings,
        )

    assert raised.value.code == "document_too_large"


def test_markdown_chunks_preserve_overlap_and_search_terms() -> None:
    settings = _settings(document_chunk_size=100, document_chunk_overlap=20)
    text = "Redis LRU " * 40

    chunks = split_document(text, settings=settings)

    assert chunks
    assert chunks[0].index == 0
    assert "redis" in chunks[0].search_text
    assert chunks[0].token_count > 0
    assert len(chunks) > 1
    assert chunks[0].content[-20:] in chunks[1].content
    assert all(len(chunk.content) <= 1200 for chunk in chunks)
