"""The only provider-facing LLM client, with bounded retries and trace records."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar
from urllib.parse import urlsplit, urlunsplit

import anthropic
import httpx
import openai
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock, ToolUseBlock
from openai import AsyncOpenAI
from openai.types.responses import ParsedResponseFunctionToolCall
from pydantic import BaseModel

from app.config import Settings
from app.llm.models import ModelTier, estimate_cost_usd, resolve_model_tier
from app.logging import get_logger
from app.trace import LlmTrace

ResultT = TypeVar("ResultT", bound=BaseModel)


class LlmClientError(Exception):
    """Stable error raised after the client exhausts its bounded retry policy."""

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class PromptMetadata:
    """Prompt identity attached to every call and trace."""

    name: str
    version: str


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """Validated provider-neutral request."""

    model: str
    system_prompt: str
    user_prompt: str
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """Only the validated data and usage details leave the provider adapter."""

    data: BaseModel
    input_tokens: int
    output_tokens: int
    finish_reason: str | None
    tool_calls: tuple[str, ...] = ()


class LlmProvider(Protocol):
    """Provider-neutral adapter contract used by the client."""

    async def generate(
        self, request: ProviderRequest, output_schema: type[BaseModel]
    ) -> ProviderResult:
        """Generate one structured output."""


@dataclass(frozen=True, slots=True)
class LlmResult(Generic[ResultT]):
    """Validated business result plus metadata safe for persistence."""

    output: ResultT
    trace: LlmTrace
    cost_usd: float


@dataclass(frozen=True, slots=True)
class TraceContext:
    """Business correlation IDs that must never contain raw prompt content."""

    request_id: str = field(default="unknown")
    trace_id: str = field(default="unknown")
    user_id_hash: str | None = None
    resume_task_id: str | None = None
    qa_request_id: str | None = None
    interview_id: str | None = None
    turn_id: str | None = None


def _parse_json_object(text: str) -> str:
    """Trim common Markdown fences without parsing arbitrary provider objects."""

    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1])
    return stripped


def _chat_completions_root(base_url: str | None) -> str | None:
    """Return the SDK base URL when configured with a full Chat Completions endpoint."""

    if not base_url:
        return None
    parsed = urlsplit(base_url.strip())
    path = parsed.path.rstrip("/")
    suffix = "/chat/completions"
    if not path.endswith(suffix):
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, path[: -len(suffix)], "", ""))


async def _generate_chat_completion(
    client: Any,
    request: ProviderRequest,
    output_schema: type[BaseModel],
    *,
    stream: bool = False,
) -> ProviderResult:
    """Call one OpenAI-compatible Chat Completions endpoint with JSON output."""

    schema_text = json.dumps(
        output_schema.model_json_schema(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    response = await client.chat.completions.create(
        model=request.model,
        messages=[
            {
                "role": "system",
                "content": (
                    f"{request.system_prompt}\n"
                    "Return one JSON object only. It must satisfy this JSON Schema:\n"
                    f"{schema_text}"
                ),
            },
            {"role": "user", "content": request.user_prompt},
        ],
        max_tokens=request.max_output_tokens,
        response_format={"type": "json_object"},
        stream=stream,
        stream_options={"include_usage": True} if stream else None,
    )
    if stream:
        text_parts: list[str] = []
        usage = None
        finish_reason = None
        tool_calls: list[str] = []
        async for chunk in response:
            if chunk.usage is not None:
                usage = chunk.usage
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            text_parts.append(choice.delta.content or "")
            finish_reason = choice.finish_reason or finish_reason
            tool_calls.extend(
                call.function.name
                for call in (choice.delta.tool_calls or [])
                if call.function and call.function.name
            )
        text = "".join(text_parts)
    else:
        choice = response.choices[0]
        text = choice.message.content or ""
        usage = response.usage
        finish_reason = choice.finish_reason
        tool_calls = [
            call.function.name for call in (choice.message.tool_calls or []) if call.function.name
        ]
    try:
        parsed = output_schema.model_validate_json(_parse_json_object(text))
    except Exception as exc:
        raise LlmClientError(
            "schema_error", "model output did not match the requested schema", retryable=True
        ) from exc
    return ProviderResult(
        data=parsed,
        input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
        output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
        finish_reason=finish_reason,
        tool_calls=tuple(tool_calls),
    )


class OpenAiProvider:
    """OpenAI SDK adapter for Responses or a full Chat Completions endpoint."""

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
            self._uses_chat_completions = _chat_completions_root(settings.llm_base_url) is not None
            return
        kwargs: dict[str, Any] = {
            "api_key": settings.llm_api_key.get_secret_value() if settings.llm_api_key else None,
            "timeout": httpx.Timeout(
                settings.llm_request_timeout_seconds,
                connect=settings.llm_connect_timeout_seconds,
            ),
            "max_retries": 0,
        }
        chat_root = _chat_completions_root(settings.llm_base_url)
        self._uses_chat_completions = chat_root is not None
        if chat_root is not None:
            kwargs["base_url"] = chat_root
        elif settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        self._client = AsyncOpenAI(**kwargs)

    async def generate(
        self, request: ProviderRequest, output_schema: type[BaseModel]
    ) -> ProviderResult:
        if self._uses_chat_completions:
            return await _generate_chat_completion(
                self._client,
                request,
                output_schema,
                stream=True,
            )
        response = await self._client.responses.parse(
            model=request.model,
            instructions=request.system_prompt,
            input=request.user_prompt,
            max_output_tokens=request.max_output_tokens,
            text_format=output_schema,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise LlmClientError(
                "schema_error", "model did not return a valid structured result", retryable=True
            )
        usage = response.usage
        tool_calls = tuple(
            item.name
            for item in response.output
            if isinstance(item, ParsedResponseFunctionToolCall)
        )
        return ProviderResult(
            data=parsed,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            finish_reason=getattr(response, "status", None),
            tool_calls=tool_calls,
        )

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            await close()


class AnthropicProvider:
    """Official Anthropic SDK adapter with JSON Schema output configuration."""

    def __init__(self, settings: Settings) -> None:
        kwargs: dict[str, Any] = {
            "api_key": settings.llm_api_key.get_secret_value() if settings.llm_api_key else None,
            "timeout": httpx.Timeout(
                settings.llm_request_timeout_seconds,
                connect=settings.llm_connect_timeout_seconds,
            ),
            "max_retries": 0,
        }
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        self._client = AsyncAnthropic(**kwargs)

    async def generate(
        self, request: ProviderRequest, output_schema: type[BaseModel]
    ) -> ProviderResult:
        response = await self._client.messages.create(
            model=request.model,
            max_tokens=request.max_output_tokens,
            system=request.system_prompt,
            messages=[{"role": "user", "content": request.user_prompt}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": output_schema.model_json_schema(),
                }
            },
        )
        text = "".join(block.text for block in response.content if isinstance(block, TextBlock))
        try:
            parsed = output_schema.model_validate_json(_parse_json_object(text))
        except Exception as exc:
            raise LlmClientError(
                "schema_error", "model output did not match the requested schema", retryable=True
            ) from exc
        usage = response.usage
        tool_calls = tuple(
            block.name for block in response.content if isinstance(block, ToolUseBlock)
        )
        return ProviderResult(
            data=parsed,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            finish_reason=response.stop_reason,
            tool_calls=tool_calls,
        )

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            await close()


class DeepSeekProvider:
    """DeepSeek's OpenAI-compatible Chat Completions adapter with JSON output."""

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
            return
        kwargs: dict[str, Any] = {
            "api_key": settings.llm_api_key.get_secret_value() if settings.llm_api_key else None,
            "timeout": httpx.Timeout(
                settings.llm_request_timeout_seconds,
                connect=settings.llm_connect_timeout_seconds,
            ),
            "max_retries": 0,
        }
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        self._client = AsyncOpenAI(**kwargs)

    async def generate(
        self, request: ProviderRequest, output_schema: type[BaseModel]
    ) -> ProviderResult:
        return await _generate_chat_completion(self._client, request, output_schema)

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            await close()


class LocalProvider:
    """Explicit non-deployment LLM provider that never calls a network service."""

    async def generate(
        self, request: ProviderRequest, output_schema: type[BaseModel]
    ) -> ProviderResult:
        raise LlmClientError(
            "local_provider_unavailable",
            f"LLM_PROVIDER=local has no generated output for {output_schema.__name__}",
            retryable=False,
        )


def _provider_from_settings(settings: Settings) -> LlmProvider:
    if settings.llm_provider == "openai":
        return OpenAiProvider(settings)
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings)
    if settings.llm_provider == "deepseek":
        return DeepSeekProvider(settings)
    if settings.llm_provider == "local" and settings.app_env in {"development", "test"}:
        return LocalProvider()
    raise ValueError(f"unsupported llm provider: {settings.llm_provider}")


class LlmClient:
    """Unified LLM entry point with timeout, retries, schema validation, and trace."""

    def __init__(
        self,
        settings: Settings,
        *,
        provider: LlmProvider | None = None,
        sleep: Any = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._provider = provider or _provider_from_settings(settings)
        self._sleep = sleep
        self._logger = get_logger("app.llm")

    async def generate(
        self,
        *,
        tier: ModelTier | str,
        prompt: PromptMetadata,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[ResultT],
        context: TraceContext,
        max_output_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ) -> LlmResult[ResultT]:
        """Generate one validated response or raise a stable client error."""

        profile = resolve_model_tier(tier, self._settings)
        request = ProviderRequest(
            model=profile.name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_output_tokens=max_output_tokens or self._settings.llm_max_output_tokens,
        )
        started = time.perf_counter()
        retry_count = 0
        last_error: LlmClientError | None = None
        timeout = min(
            timeout_seconds or self._settings.llm_request_timeout_seconds,
            self._settings.llm_request_timeout_seconds,
        )
        deadline = time.monotonic() + timeout
        for attempt in range(self._settings.llm_max_retries + 1):
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                async with asyncio.timeout(remaining):
                    result = await self._provider.generate(request, output_schema)
                validated = output_schema.model_validate(result.data)
                latency_ms = round((time.perf_counter() - started) * 1000)
                trace = LlmTrace(
                    request_id=context.request_id,
                    trace_id=context.trace_id,
                    model_tier=profile.tier.value,
                    model_name=profile.name,
                    prompt_name=prompt.name,
                    prompt_version=prompt.version,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    latency_ms=latency_ms,
                    retry_count=retry_count,
                    tool_calls=result.tool_calls,
                    finish_reason=result.finish_reason,
                    user_id_hash=context.user_id_hash,
                    resume_task_id=context.resume_task_id,
                    qa_request_id=context.qa_request_id,
                    interview_id=context.interview_id,
                    turn_id=context.turn_id,
                )
                cost = estimate_cost_usd(profile, result.input_tokens, result.output_tokens)
                self._logger.info("llm call completed", **trace.as_log_fields())
                return LlmResult(output=validated, trace=trace, cost_usd=float(cost))
            except asyncio.CancelledError:
                raise
            except (
                TimeoutError,
                httpx.TimeoutException,
                openai.APITimeoutError,
                anthropic.APITimeoutError,
            ) as exc:
                last_error = LlmClientError("timeout", "model request timed out", retryable=True)
                last_error.__cause__ = exc
            except (openai.RateLimitError, anthropic.RateLimitError) as exc:
                last_error = LlmClientError(
                    "rate_limited", "model provider rate limit reached", retryable=True
                )
                last_error.__cause__ = exc
            except (
                openai.APIConnectionError,
                openai.InternalServerError,
                anthropic.APIConnectionError,
                anthropic.InternalServerError,
                anthropic.ServiceUnavailableError,
                anthropic.OverloadedError,
                anthropic.DeadlineExceededError,
            ) as exc:
                last_error = LlmClientError(
                    "provider_unavailable", "model provider is unavailable", retryable=True
                )
                last_error.__cause__ = exc
            except (openai.BadRequestError, anthropic.BadRequestError) as exc:
                last_error = LlmClientError(
                    "invalid_request", "model provider rejected the request", retryable=False
                )
                last_error.__cause__ = exc
            except LlmClientError as exc:
                last_error = exc
            except Exception as exc:
                last_error = LlmClientError("provider_error", "model call failed", retryable=False)
                last_error.__cause__ = exc

            if not last_error.retryable or attempt >= self._settings.llm_max_retries:
                break
            retry_count += 1
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await self._sleep(min(0.25 * (2**attempt), 2.0, remaining))

        assert last_error is not None
        trace = LlmTrace(
            request_id=context.request_id,
            trace_id=context.trace_id,
            model_tier=profile.tier.value,
            model_name=profile.name,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            input_tokens=0,
            output_tokens=0,
            latency_ms=round((time.perf_counter() - started) * 1000),
            retry_count=retry_count,
            error_code=last_error.code,
            user_id_hash=context.user_id_hash,
            resume_task_id=context.resume_task_id,
            qa_request_id=context.qa_request_id,
            interview_id=context.interview_id,
            turn_id=context.turn_id,
        )
        self._logger.warning("llm call failed", **trace.as_log_fields())
        raise last_error

    async def aclose(self) -> None:
        """Release provider-owned network resources."""

        close = getattr(self._provider, "close", None)
        if callable(close):
            await close()
