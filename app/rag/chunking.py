"""Deterministic chunking and lexical search text generation."""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.config import Settings
from app.rag.contracts import DocumentChunk

_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_+#.-]+|[\u4e00-\u9fff]")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？.!?])\s+|\n{2,}")
_MAX_CHUNK_CHARACTERS = 1200


def _search_text(content: str) -> str:
    tokens = [token.casefold() for token in _TOKEN_PATTERN.findall(content)]
    return " ".join(tokens)


def _segments(text: str) -> list[str]:
    segments = [item.strip() for item in _SENTENCE_BOUNDARY.split(text) if item.strip()]
    return segments or [text]


def _window(
    segments: Iterable[str],
    *,
    size: int,
    overlap: int,
) -> list[str]:
    chunks: list[str] = []
    current = ""
    for segment in segments:
        candidate = f"{current}\n{segment}".strip() if current else segment
        if len(candidate) <= size:
            current = candidate
            continue
        if current:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n{segment}".strip()
        else:
            current = segment
        while len(current) > size:
            chunks.append(current[:size])
            current = current[size - overlap :] if overlap else current[size:]
    if current.strip():
        chunks.append(current.strip())
    return [chunk[:_MAX_CHUNK_CHARACTERS] for chunk in chunks if chunk.strip()]


def split_document(text: str, *, settings: Settings) -> list[DocumentChunk]:
    """Split normalized text into stable overlapping chunks."""

    normalized = text.strip()
    if not normalized:
        return []
    chunks = _window(
        _segments(normalized),
        size=settings.document_chunk_size,
        overlap=settings.document_chunk_overlap,
    )
    return [
        DocumentChunk(
            index=index,
            section_path=f"正文 / {index + 1}",
            content=content,
            search_text=_search_text(content),
            token_count=max(1, len(_search_text(content).split())),
        )
        for index, content in enumerate(chunks)
    ]
