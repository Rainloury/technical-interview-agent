"""LLM client timeout, retry, validation, cancellation, and trace tests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any, cast

import anthropic
import httpx
import pytest
import respx
from app.config import Settings
from app.llm.client import (
    DeepSeekProvider,
    LlmClient,
    LlmClientError,
    LlmResult,
    OpenAiProvider,
    PromptMetadata,
    ProviderRequest,
    ProviderResult,
    TraceContext,
    _chat_completions_root,
)
from openai.types.chat import ChatCompletionChunk
from pydantic import BaseModel


class Output(BaseModel):
    answer: str


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        (
            "https://copilot.tencent.com/v2/chat/completions",
            "https://copilot.tencent.com/v2",
        ),
        (
            "https://copilot.tencent.com/v2/chat/completions/",
            "https://copilot.tencent.com/v2",
        ),
        ("https://api.openai.com/v1", None),
        (None, None),
    ],
)
def test_chat_completions_root_only_normalizes_full_endpoints(
    base_url: str | None,
    expected: str | None,
) -> None:
    assert _chat_completions_root(base_url) == expected


class FakeProvider:
    def __init__(
        self,
        outcomes: list[ProviderResult | Exception],
    ) -> None:
        self.outcomes = outcomes
        self.calls = 0

    async def generate(
        self, request: ProviderRequest, output_schema: type[BaseModel]
    ) -> ProviderResult:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeStream:
    def __init__(self, chunks: list[ChatCompletionChunk]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> FakeStream:
        return self

    async def __anext__(self) -> ChatCompletionChunk:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class BlockingProvider:
    async def generate(
        self, request: ProviderRequest, output_schema: type[BaseModel]
    ) -> ProviderResult:
        await asyncio.sleep(10)
        raise AssertionError("timeout did not cancel the provider call")


def _success(answer: str = "ok") -> ProviderResult:
    return ProviderResult(
        data=Output(answer=answer),
        input_tokens=10,
        output_tokens=4,
        finish_reason="completed",
        tool_calls=("search",),
    )


async def _no_sleep(_seconds: float) -> None:
    return None


async def _generate(
    client: LlmClient,
    *,
    context: TraceContext | None = None,
    max_output_tokens: int | None = None,
) -> LlmResult[Output]:
    return await client.generate(
        tier="FAST",
        prompt=PromptMetadata(name="agent_turn", version="1.0.0"),
        system_prompt="system",
        user_prompt="user",
        output_schema=Output,
        context=context or TraceContext(request_id="req_1", trace_id="trace_1"),
        max_output_tokens=max_output_tokens,
    )


async def test_client_returns_validated_output_and_complete_trace() -> None:
    provider = FakeProvider([_success()])
    settings = Settings(llm_max_retries=2)
    client = LlmClient(settings, provider=provider, sleep=_no_sleep)

    result = await client.generate(
        tier="DEFAULT",
        prompt=PromptMetadata(name="agent_turn", version="1.0.0"),
        system_prompt="system",
        user_prompt="user",
        output_schema=Output,
        context=TraceContext(
            request_id="req_1",
            trace_id="trace_1",
            interview_id="interview_1",
        ),
    )

    assert isinstance(result.output, Output)
    assert result.output.answer == "ok"
    assert result.trace.request_id == "req_1"
    assert result.trace.input_tokens == 10
    assert result.trace.output_tokens == 4
    assert result.trace.tool_calls == ("search",)
    assert result.trace.interview_id == "interview_1"
    assert result.cost_usd > 0


async def test_client_retries_recoverable_schema_failure() -> None:
    provider = FakeProvider(
        [
            LlmClientError("schema_error", "bad shape", retryable=True),
            _success("fixed"),
        ]
    )
    client = LlmClient(Settings(llm_max_retries=1), provider=provider, sleep=_no_sleep)

    result = await _generate(client)

    assert result.output.answer == "fixed"
    assert result.trace.retry_count == 1
    assert provider.calls == 2


async def test_client_stops_after_retry_budget() -> None:
    provider = FakeProvider(
        [
            LlmClientError("provider_unavailable", "down", retryable=True),
            LlmClientError("provider_unavailable", "down", retryable=True),
        ]
    )
    client = LlmClient(Settings(llm_max_retries=1), provider=provider, sleep=_no_sleep)

    with pytest.raises(LlmClientError) as raised:
        await _generate(client)

    assert raised.value.code == "provider_unavailable"
    assert provider.calls == 2


async def test_non_retryable_error_is_not_retried() -> None:
    provider = FakeProvider([LlmClientError("invalid_request", "bad", retryable=False)])
    client = LlmClient(Settings(llm_max_retries=3), provider=provider, sleep=_no_sleep)

    with pytest.raises(LlmClientError):
        await _generate(client)

    assert provider.calls == 1


@pytest.mark.parametrize(
    ("provider_error", "expected_code", "expected_calls"),
    [
        (
            anthropic.RateLimitError(
                "limited",
                response=httpx.Response(
                    429,
                    request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
                ),
                body=None,
            ),
            "rate_limited",
            2,
        ),
        (
            anthropic.APITimeoutError(
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            ),
            "timeout",
            2,
        ),
    ],
)
async def test_anthropic_transient_errors_are_mapped_and_retried(
    provider_error: Exception,
    expected_code: str,
    expected_calls: int,
) -> None:
    provider = FakeProvider([provider_error, provider_error])
    client = LlmClient(Settings(llm_max_retries=1), provider=provider, sleep=_no_sleep)

    with pytest.raises(LlmClientError) as raised:
        await _generate(client)

    assert raised.value.code == expected_code
    assert raised.value.retryable is True
    assert provider.calls == expected_calls


async def test_total_timeout_cancels_the_provider_call() -> None:
    client = LlmClient(
        Settings(llm_request_timeout_seconds=0.01, llm_max_retries=0),
        provider=BlockingProvider(),
        sleep=_no_sleep,
    )

    with pytest.raises(LlmClientError) as raised:
        await _generate(client)

    assert raised.value.code == "timeout"


async def test_cancellation_propagates_without_becoming_provider_error() -> None:
    cancelled = asyncio.Event()

    class CancelProvider:
        async def generate(
            self, request: ProviderRequest, output_schema: type[BaseModel]
        ) -> ProviderResult:
            cancelled.set()
            await asyncio.sleep(10)
            return _success()

    client = LlmClient(Settings(), provider=CancelProvider(), sleep=_no_sleep)
    task = asyncio.create_task(_generate(client))
    await cancelled.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_output_is_validated_by_client_even_if_provider_is_loose() -> None:
    class LooseProvider:
        async def generate(
            self, request: ProviderRequest, output_schema: type[BaseModel]
        ) -> ProviderResult:
            return ProviderResult(
                data=Output(answer="valid"),
                input_tokens=1,
                output_tokens=1,
                finish_reason="completed",
            )

    client = LlmClient(Settings(), provider=LooseProvider(), sleep=_no_sleep)
    result = await _generate(client)

    assert isinstance(result.output, Output)


def test_sleep_function_signature_is_awaitable_compatible() -> None:
    callback: Callable[[float], Awaitable[None]] = _no_sleep
    assert callable(callback)


async def test_deepseek_adapter_uses_json_mode_and_maps_usage() -> None:
    calls: list[dict[str, object]] = []

    class FakeCompletions:
        async def create(self, **kwargs: object) -> object:
            calls.append(kwargs)
            message = SimpleNamespace(
                content='{"answer":"ok"}',
                tool_calls=[SimpleNamespace(function=SimpleNamespace(name="search"))],
            )
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=message,
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=12, completion_tokens=5),
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions()),
    )
    provider = DeepSeekProvider(
        Settings(llm_provider="deepseek", llm_base_url="https://api.deepseek.com"),
        client=cast(Any, fake_client),
    )

    result = await provider.generate(
        ProviderRequest(
            model="deepseek-flash",
            system_prompt="system",
            user_prompt="user",
            max_output_tokens=128,
        ),
        Output,
    )

    assert result.data == Output(answer="ok")
    assert result.input_tokens == 12
    assert result.output_tokens == 5
    assert result.tool_calls == ("search",)
    assert calls[0]["response_format"] == {"type": "json_object"}


@respx.mock
async def test_openai_adapter_uses_full_chat_endpoint_once() -> None:
    sse = (
        'data: {"id":"chunk-1","object":"chat.completion.chunk","created":1,'
        '"model":"deepseek-v4.1-flash","choices":[{"index":0,"delta":'
        '{"role":"assistant","content":"{\\"answer\\":\\"ok\\"}"},"finish_reason":"stop"}],'
        '"usage":null}\n\n'
        'data: {"id":"chunk-2","object":"chat.completion.chunk","created":1,'
        '"model":"deepseek-v4.1-flash","choices":[],"usage":'
        '{"prompt_tokens":12,"completion_tokens":5,"total_tokens":17}}\n\n'
        "data: [DONE]\n\n"
    )
    route = respx.post("https://copilot.tencent.com/v2/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text=sse,
        )
    )
    provider = OpenAiProvider(
        Settings(
            llm_provider="openai",
            llm_api_key="test-key",
            llm_base_url="https://copilot.tencent.com/v2/chat/completions",
        )
    )

    try:
        result = await provider.generate(
            ProviderRequest(
                model="deepseek-v4.1-flash",
                system_prompt="system",
                user_prompt="user",
                max_output_tokens=128,
            ),
            Output,
        )
    finally:
        await provider.close()

    assert route.call_count == 1
    assert result.data == Output(answer="ok")
    assert result.input_tokens == 12
    assert result.output_tokens == 5
    assert result.finish_reason == "stop"


async def test_openai_chat_provider_accumulates_streamed_content_and_usage() -> None:
    calls: list[dict[str, object]] = []
    chunks = [
        ChatCompletionChunk.model_validate(
            {
                "id": "chunk-1",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "deepseek-v4.1-flash",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": '{"answer":'},
                        "finish_reason": None,
                    }
                ],
                "usage": None,
            }
        ),
        ChatCompletionChunk.model_validate(
            {
                "id": "chunk-2",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "deepseek-v4.1-flash",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": '"streamed"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": None,
            }
        ),
        ChatCompletionChunk.model_validate(
            {
                "id": "chunk-3",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "deepseek-v4.1-flash",
                "choices": [],
                "usage": {
                    "prompt_tokens": 21,
                    "completion_tokens": 7,
                    "total_tokens": 28,
                },
            }
        ),
    ]

    class FakeCompletions:
        async def create(self, **kwargs: object) -> FakeStream:
            calls.append(kwargs)
            return FakeStream(chunks)

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions()),
    )
    provider = OpenAiProvider(
        Settings(
            llm_provider="openai",
            llm_api_key="test-key",
            llm_base_url="https://copilot.tencent.com/v2/chat/completions",
            _env_file=None,
        ),
        client=fake_client,
    )

    result = await provider.generate(
        ProviderRequest(
            model="deepseek-v4.1-flash",
            system_prompt="system",
            user_prompt="user",
            max_output_tokens=128,
        ),
        Output,
    )

    assert result.data == Output(answer="streamed")
    assert result.input_tokens == 21
    assert result.output_tokens == 7
    assert result.finish_reason == "stop"
    assert calls[0]["stream"] is True
    assert calls[0]["stream_options"] == {"include_usage": True}
