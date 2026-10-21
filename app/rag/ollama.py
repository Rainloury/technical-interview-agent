"""Bounded Ollama embedding client isolated from chat model routing."""

from __future__ import annotations

import asyncio
import json
import math
from typing import Protocol

import httpx

from app.config import Settings


class OllamaEmbeddingError(Exception):
    """Stable embedding failure with retry semantics."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class EmbeddingClient(Protocol):
    """Narrow embedding contract consumed by ingestion and retrieval."""

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbeddingClient:
    """Ollama `/api/embed` adapter with batching, retry, and dimension checks."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if settings.ollama_base_url is None:
            raise ValueError("OLLAMA_BASE_URL is required for embeddings")
        self._settings = settings
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                settings.ollama_request_timeout_seconds,
                connect=settings.ollama_connect_timeout_seconds,
            )
        )
        self._owns_client = client is None

    async def _request(self, texts: list[str]) -> list[list[float]]:
        for attempt in range(self._settings.ollama_max_retries + 1):
            try:
                response = await self._client.post(
                    f"{self._base_url}/api/embed",
                    json={
                        "model": self._settings.ollama_embedding_model,
                        "input": texts,
                    },
                )
            except httpx.TimeoutException as exc:
                if attempt >= self._settings.ollama_max_retries:
                    raise OllamaEmbeddingError("embedding_timeout", retryable=True) from exc
                await asyncio.sleep(min(2**attempt, 4))
                continue
            except httpx.HTTPError as exc:
                if attempt >= self._settings.ollama_max_retries:
                    raise OllamaEmbeddingError("embedding_unavailable", retryable=True) from exc
                await asyncio.sleep(min(2**attempt, 4))
                continue
            if response.status_code >= 400:
                retryable = response.status_code == 429 or response.status_code >= 500
                if retryable and attempt < self._settings.ollama_max_retries:
                    await asyncio.sleep(min(2**attempt, 4))
                    continue
                code = (
                    "embedding_rate_limited"
                    if response.status_code == 429
                    else "embedding_unavailable"
                    if response.status_code >= 500
                    else "embedding_invalid_request"
                )
                raise OllamaEmbeddingError(code, retryable=retryable)
            try:
                payload = response.json()
                embeddings = payload["embeddings"]
                if not isinstance(embeddings, list):
                    raise TypeError
                vectors = [[float(value) for value in item] for item in embeddings]
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise OllamaEmbeddingError("embedding_invalid_response", retryable=False) from exc
            if len(vectors) != len(texts):
                raise OllamaEmbeddingError("embedding_count_mismatch", retryable=False)
            for vector in vectors:
                if len(vector) != self._settings.ollama_embedding_dimensions:
                    raise OllamaEmbeddingError(
                        "embedding_dimension_mismatch",
                        retryable=False,
                    )
                if any(not math.isfinite(value) for value in vector):
                    raise OllamaEmbeddingError("embedding_invalid_response", retryable=False)
            return vectors
        raise OllamaEmbeddingError("embedding_unavailable", retryable=True)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in bounded batches while preserving input order."""

        if not texts:
            return []
        vectors: list[list[float]] = []
        batch_size = self._settings.rag_embedding_batch_size
        for start in range(0, len(texts), batch_size):
            vectors.extend(await self._request(texts[start : start + batch_size]))
        return vectors

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
