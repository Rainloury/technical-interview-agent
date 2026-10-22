"""Ollama embedding request, retry, and validation tests."""

from __future__ import annotations

import json

import httpx
import pytest
from app.config import Settings
from app.rag.ollama import OllamaEmbeddingClient, OllamaEmbeddingError


def _settings(**values: object) -> Settings:
    return Settings(
        app_env="test",
        ollama_base_url="http://ollama.test:11434",
        ollama_embedding_dimensions=1024,
        ollama_max_retries=1,
        _env_file=None,
        **values,
    )


@pytest.mark.asyncio
async def test_ollama_embedding_validates_dimension_and_retries_transient() -> None:
    calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            json={"embeddings": [[0.0] * 1024]},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OllamaEmbeddingClient(_settings(), client=http)
        vectors = await client.embed(["Redis 设计"])
        await client.aclose()

    assert len(calls) == 2
    assert calls[0]["model"] == "mxbai-embed-large:latest"
    assert vectors[0][0] == 0.0
    assert len(vectors[0]) == 1024


@pytest.mark.asyncio
async def test_ollama_embedding_rejects_dimension_mismatch_without_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"embeddings": [[0.0] * 3]},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OllamaEmbeddingClient(_settings(), client=http)
        with pytest.raises(OllamaEmbeddingError) as raised:
            await client.embed(["bad dimension"])

    assert raised.value.code == "embedding_dimension_mismatch"
    assert raised.value.retryable is False
    assert calls == 1


@pytest.mark.asyncio
async def test_ollama_embedding_does_not_retry_permanent_client_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OllamaEmbeddingClient(_settings(), client=http)
        with pytest.raises(OllamaEmbeddingError) as raised:
            await client.embed(["bad request"])

    assert raised.value.retryable is False
    assert raised.value.code == "embedding_invalid_request"
    assert calls == 1


@pytest.mark.asyncio
async def test_ollama_embedding_batches_inputs() -> None:
    batches: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        input_values = payload["input"]
        assert isinstance(input_values, list)
        batches.append(input_values)
        return httpx.Response(
            200,
            json={"embeddings": [[0.0] * 1024 for _ in input_values]},
            request=request,
        )

    settings = _settings(rag_embedding_batch_size=2)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OllamaEmbeddingClient(settings, client=http)
        vectors = await client.embed(["a", "b", "c"])

    assert [len(batch) for batch in batches] == [2, 1]
    assert len(vectors) == 3
