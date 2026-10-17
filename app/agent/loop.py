"""Bounded plan -> act -> observe loop with structured decisions."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.registry import RegistryError, ToolRegistry
from app.llm.client import LlmClient, LlmClientError, PromptMetadata, TraceContext
from app.llm.models import ModelTier
from app.prompts.loader import PromptLoader
from app.tools._base import error_envelope, normalize_tool_result, wrap_untrusted


class AgentDecision(BaseModel):
    """The model's next bounded step."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["tool", "finish", "fail"]
    tool_name: str | None = None
    arguments: dict[str, object] = Field(default_factory=dict)
    answer: str | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class AgentLimits:
    """Hard limits applied to every loop."""

    max_steps: int = 8
    max_tokens: int = 200_000
    timeout_seconds: float = 60.0
    max_depth: int = 2

    def validate(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be at least 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 1 <= self.max_depth <= 2:
            raise ValueError("max_depth must be between 1 and 2")


class AgentLimitError(RuntimeError):
    """A hard budget or cycle limit was reached."""


@dataclass(frozen=True, slots=True)
class AgentObservation:
    """Serializable observation fed back to the next model step."""

    step: int
    tool_name: str
    result: object


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    """Final bounded agent result and aggregate accounting."""

    answer: str
    steps: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    observations: tuple[AgentObservation, ...]
    stop_reason: str = "finished"


class AgentLoop:
    """Single iteration point for all agent work."""

    def __init__(
        self,
        *,
        client: LlmClient,
        registry: ToolRegistry,
        prompts: PromptLoader,
        limits: AgentLimits | None = None,
        tool_result_dir: str | None = None,
        tool_result_max_chars: int = 2000,
    ) -> None:
        self._client = client
        self._registry = registry
        self._prompts = prompts
        self._limits = limits or AgentLimits()
        self._limits.validate()
        self._tool_result_dir = tool_result_dir
        self._tool_result_max_chars = tool_result_max_chars

    def _budget_check(self, used_tokens: int, next_estimate: int) -> None:
        if next_estimate > self._limits.max_tokens - used_tokens:
            raise AgentLimitError("token budget exhausted")

    async def run(
        self,
        task: str,
        *,
        context: TraceContext | None = None,
        depth: int = 0,
        tier: ModelTier | str = ModelTier.DEFAULT,
    ) -> AgentRunResult:
        """Run until the model finishes, fails, or a hard limit is reached."""

        if depth > self._limits.max_depth:
            raise AgentLimitError("maximum nesting depth exceeded")
        started = time.monotonic()
        observations: list[AgentObservation] = []
        used_input = 0
        used_output = 0
        cost = 0.0
        system_prompt = self._prompts.load("agent_system")
        turn_prompt = self._prompts.load("agent_turn")
        tool_text = json.dumps(
            self._registry.schemas(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        for step in range(1, self._limits.max_steps + 1):
            elapsed = time.monotonic() - started
            if elapsed >= self._limits.timeout_seconds:
                raise AgentLimitError("agent timeout reached")
            if used_input + used_output >= self._limits.max_tokens:
                raise AgentLimitError("token budget exhausted")
            observation_text = "\n".join(
                f"{item.step}. {item.tool_name}: {wrap_untrusted(str(item.result))}"
                for item in observations
            )
            user_prompt = turn_prompt.render(
                task=task,
                tools=tool_text,
                observations=observation_text or "(none)",
            )
            prompt_estimate = (len(system_prompt.body) + len(user_prompt)) // 4
            self._budget_check(used_input + used_output, prompt_estimate)
            try:
                async with asyncio.timeout(max(0.01, self._limits.timeout_seconds - elapsed)):
                    result = await self._client.generate(
                        tier=tier,
                        prompt=PromptMetadata(
                            name="agent_turn",
                            version=turn_prompt.version,
                        ),
                        system_prompt=system_prompt.body,
                        user_prompt=user_prompt,
                        output_schema=AgentDecision,
                        context=context or TraceContext(),
                        timeout_seconds=max(0.01, self._limits.timeout_seconds - elapsed),
                    )
            except LlmClientError:
                raise
            except TimeoutError as exc:
                raise AgentLimitError("agent timeout reached") from exc
            used_input += result.trace.input_tokens
            used_output += result.trace.output_tokens
            cost += result.cost_usd
            if used_input + used_output > self._limits.max_tokens:
                raise AgentLimitError("token budget exhausted")
            decision = AgentDecision.model_validate(result.output)
            if decision.kind == "finish":
                return AgentRunResult(
                    answer=decision.answer or "",
                    steps=step,
                    input_tokens=used_input,
                    output_tokens=used_output,
                    cost_usd=cost,
                    observations=tuple(observations),
                )
            if decision.kind == "fail":
                raise AgentLimitError(decision.reason or "agent reported failure")
            if not decision.tool_name:
                raise RegistryError("tool decision requires tool_name")
            try:
                raw = await self._registry.execute(
                    decision.tool_name,
                    decision.arguments,
                    dry_run=True,
                )
                result_value = normalize_tool_result(
                    raw,
                    max_chars=self._tool_result_max_chars,
                    result_dir=self._tool_result_dir,
                )
            except (RegistryError, ValidationError) as exc:
                result_value = error_envelope(exc)
            except Exception as exc:
                result_value = error_envelope(exc)
            observations.append(
                AgentObservation(
                    step=step,
                    tool_name=decision.tool_name,
                    result=result_value,
                )
            )
        raise AgentLimitError("maximum agent steps reached")
