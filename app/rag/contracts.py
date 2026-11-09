"""文档摄取与检索共享的纯数据契约。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    """从单个私有文档中提取的已验证文本。"""

    detected_mime: str
    text: str
    page_count: int | None


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    """一个稳定、可检索的文档分块。"""

    index: int
    section_path: str
    content: str
    search_text: str
    token_count: int
