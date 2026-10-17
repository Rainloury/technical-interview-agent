"""Bounded agent loop success, tool feedback, and limit tests."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from app.agent.loop import AgentLimitError, AgentLimits, AgentLoop
from app.agent.registry import RegisteredTool, ToolRegistry
from app.config import Settings
from app.llm.client import (
    LlmClient,
    ProviderRequest,
    ProviderResult,
    TraceContext,
)
from app.prompts.loader import PromptLoader
from app.tools._base import ToolParams
from pydantic import BaseModel

PROMPTS = Path(__file__).resolve().parents[1] / "app" / "prompts"


class SearchParams(ToolParams):
    query: str


async def search(params: SearchParams) -> dict[str, str]:
    return {"query": params.query, "result": "x" * 3000}


class ScriptedProvider:
    def __init__(self, decisions: Sequence[dict[str, Any]], tokens: tuple[int, int] = (1, 1)):
        self.decisions = list(decisions)
        self.tokens = tokens
        self.requests: list[ProviderRequest] = []

    async def generate(
        self, request: ProviderRequest, output_schema: type[BaseModel]
    ) -> ProviderResult:
        self.requests.append(request)
        decision = self.decisions.pop(0)
        return ProviderResult(
            data=output_schema.model_validate(decision),
            input_tokens=self.tokens[0],
            output_tokens=self.tokens[1],
            finish_reason="completed",
        )


async def _sleep(_seconds: float) -> None:
    return None


def _loop(
    provider: ScriptedProvider,
    *,
    limits: AgentLimits | None = None,
    result_dir: Path | None = None,
) -> AgentLoop:
    registry = ToolRegistry(
        [
            RegisteredTool(
                name="search",
                description="Use for lookup; do not use for writes.",
                params=SearchParams,
                func=search,
            )
        ]
    )
    client = LlmClient(Settings(), provider=provider, sleep=_sleep)
    return AgentLoop(
        client=client,
        registry=registry,
        prompts=PromptLoader(PROMPTS),
        limits=limits,
        tool_result_dir=str(result_dir) if result_dir else None,
    )


async def test_loop_observes_tool_result_then_finishes(tmp_path: Path) -> None:
    provider = ScriptedProvider(
        [
            {
                "kind": "tool",
                "tool_name": "search",
                "arguments": {"query": "transactions"},
            },
            {"kind": "finish", "answer": "done"},
        ]
    )
    loop = _loop(provider, result_dir=tmp_path)

    result = await loop.run("find an answer", context=TraceContext(request_id="req_1"))

    assert result.answer == "done"
    assert result.steps == 2
    assert len(result.observations) == 1
    assert result.observations[0].result["truncated"] is True  # type: ignore[index]
    assert '"parameters"' in provider.requests[0].user_prompt
    assert '"required":["query"]' in provider.requests[0].user_prompt
    assert "<untrusted>" in provider.requests[1].user_prompt
    assert "x" * 200 not in provider.requests[1].user_prompt


async def test_unregistered_tool_error_is_fed_back_not_raised() -> None:
    provider = ScriptedProvider(
        [
            {"kind": "tool", "tool_name": "dynamic.tool", "arguments": {}},
            {"kind": "finish", "answer": "recovered"},
        ]
    )
    loop = _loop(provider)

    result = await loop.run("test")

    assert result.answer == "recovered"
    assert result.observations[0].result["ok"] is False  # type: ignore[index]


async def test_max_steps_is_a_hard_limit() -> None:
    provider = ScriptedProvider(
        [{"kind": "tool", "tool_name": "search", "arguments": {"query": "x"}}] * 3
    )
    loop = _loop(provider, limits=AgentLimits(max_steps=2, max_tokens=1000, timeout_seconds=10))

    with pytest.raises(AgentLimitError, match="maximum agent steps"):
        await loop.run("loop forever")


async def test_token_budget_is_checked_before_and_after_call() -> None:
    provider = ScriptedProvider(
        [
            {"kind": "finish", "answer": "one"},
            {"kind": "finish", "answer": "two"},
        ],
        tokens=(80, 40),
    )
    loop = _loop(provider, limits=AgentLimits(max_steps=2, max_tokens=100, timeout_seconds=10))

    with pytest.raises(AgentLimitError, match="token budget"):
        await loop.run("use tokens")


async def test_nested_depth_above_two_is_rejected() -> None:
    provider = ScriptedProvider([{"kind": "finish", "answer": "no"}])
    loop = _loop(provider)

    with pytest.raises(AgentLimitError, match="nesting depth"):
        await loop.run("nested", depth=3)


async def test_timeout_is_a_hard_limit() -> None:
    class SlowProvider(ScriptedProvider):
        async def generate(
            self, request: ProviderRequest, output_schema: type[BaseModel]
        ) -> ProviderResult:
            await asyncio.sleep(1)
            return await super().generate(request, output_schema)

    provider = SlowProvider([{"kind": "finish", "answer": "late"}])
    loop = _loop(
        provider,
        limits=AgentLimits(max_steps=1, max_tokens=1000, timeout_seconds=0.01),
    )

    with pytest.raises((AgentLimitError, TimeoutError), match="timeout"):
        await loop.run("slow")
