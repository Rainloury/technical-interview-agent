"""Optional live-provider behavior check, isolated from deterministic tests."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.agent.loop import AgentLoop
from app.agent.registry import RegisteredTool, ToolRegistry
from app.config import Settings
from app.llm.client import LlmClient, TraceContext
from app.llm.models import ModelTier, resolve_model_tier
from app.prompts.loader import PromptLoader
from app.tools._base import ToolParams

DEFAULT_OUTPUT = Path("/private/tmp/technical-interview-agent-provider-eval.json")


class AddParams(ToolParams):
    """Small deterministic tool used to observe provider tool selection."""

    left: int
    right: int


async def add(params: AddParams) -> dict[str, int]:
    """Return a deterministic arithmetic result."""

    return {"sum": params.left + params.right}


@dataclass(frozen=True, slots=True)
class ProviderEvidence:
    """One live provider run's observable outcome and cost."""

    status: Literal["passed", "failed"]
    provider: str
    model: str
    tier: str
    started_at: str
    prompt_version: str | None
    system_prompt_version: str | None = None
    turn_prompt_version: str | None = None
    answer: str | None = None
    steps: int = 0
    tool_calls: tuple[str, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    failure_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _provider_is_configured(settings: Settings) -> bool:
    key = settings.llm_api_key.get_secret_value().strip() if settings.llm_api_key else ""
    return bool(key)


async def run_provider_check(
    settings: Settings,
    *,
    tier: ModelTier | str = ModelTier.FAST,
) -> ProviderEvidence:
    """Execute one real provider call through the shared Agent Loop."""

    if not _provider_is_configured(settings):
        raise ValueError("LLM_API_KEY is required for the live provider eval")

    resolved_tier = ModelTier(tier)
    profile = resolve_model_tier(resolved_tier, settings)
    loader = PromptLoader(settings.prompt_dir)
    system_prompt = loader.load("agent_system")
    turn_prompt = loader.load("agent_turn")
    prompt_version = f"agent_system@{system_prompt.version}+agent_turn@{turn_prompt.version}"
    registry = ToolRegistry(
        [
            RegisteredTool(
                name="add",
                description=(
                    "Use only to calculate the supplied two integers; never use for other requests."
                ),
                params=AddParams,
                func=add,
            )
        ]
    )
    loop = AgentLoop(
        client=LlmClient(settings),
        registry=registry,
        prompts=loader,
    )
    started = datetime.now(UTC)
    try:
        result = await loop.run(
            "Use the add tool to calculate 17 + 25, then return the numeric sum.",
            context=TraceContext(request_id="eval_provider", trace_id="trace_eval_provider"),
            tier=resolved_tier,
        )
    except Exception as exc:
        return ProviderEvidence(
            status="failed",
            provider=profile.provider,
            model=profile.name,
            tier=resolved_tier.value,
            started_at=started.isoformat(),
            prompt_version=prompt_version,
            system_prompt_version=system_prompt.version,
            turn_prompt_version=turn_prompt.version,
            failure_reason=f"{type(exc).__name__}: {exc}",
        )

    tool_calls = tuple(item.tool_name for item in result.observations)
    answer = result.answer
    failure_reason = None
    if tool_calls != ("add",):
        failure_reason = f"unexpected tool calls: {tool_calls!r}"
    elif "42" not in answer:
        failure_reason = f"answer does not contain the expected sum: {answer!r}"
    return ProviderEvidence(
        status="passed" if failure_reason is None else "failed",
        provider=profile.provider,
        model=profile.name,
        tier=resolved_tier.value,
        started_at=started.isoformat(),
        prompt_version=prompt_version,
        system_prompt_version=system_prompt.version,
        turn_prompt_version=turn_prompt.version,
        answer=answer,
        steps=result.steps,
        tool_calls=tool_calls,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        latency_ms=round((datetime.now(UTC) - started).total_seconds() * 1000),
        failure_reason=failure_reason,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=[tier.value for tier in ModelTier], default="FAST")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one live model task and persist non-secret evidence."""

    args = _parser().parse_args(argv)
    try:
        evidence = asyncio.run(run_provider_check(Settings(app_env="test"), tier=args.tier))
    except Exception as exc:
        sys.stderr.write(f"provider eval could not run: {type(exc).__name__}: {exc}\n")
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sys.stdout.write(json.dumps(evidence.as_dict(), ensure_ascii=False, indent=2) + "\n")
    return 0 if evidence.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
