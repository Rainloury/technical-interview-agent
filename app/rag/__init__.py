"""Private-document retrieval primitives."""

from app.rag.chunking import split_document
from app.rag.contracts import DocumentChunk, ExtractedDocument
from app.rag.extraction import extract_document
from app.rag.ollama import EmbeddingClient, OllamaEmbeddingClient, OllamaEmbeddingError

__all__ = [
    "DocumentChunk",
    "EmbeddingClient",
    "ExtractedDocument",
    "OllamaEmbeddingClient",
    "OllamaEmbeddingError",
    "extract_document",
    "split_document",
]
