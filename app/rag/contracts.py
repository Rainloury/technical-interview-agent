"""Pure data contracts shared by document ingestion and retrieval."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    """Validated text extracted from one private document."""

    detected_mime: str
    text: str
    page_count: int | None


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    """One stable, retrievable document chunk."""

    index: int
    section_path: str
    content: str
    search_text: str
    token_count: int
