"""Central model tiers, provider mappings, and pricing metadata."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.config import Settings


class ModelTier(StrEnum):
    """Stable tiers consumed by application code."""

    FAST = "FAST"
    DEFAULT = "DEFAULT"
    REASONING = "REASONING"


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """One resolved model and its cost metadata."""

    tier: ModelTier
    provider: str
    name: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal


@dataclass(frozen=True, slots=True)
class ModelTierMapping:
    """Provider defaults that can be overridden by environment configuration."""

    provider: str
    names: tuple[str, str, str]
    pricing: tuple[tuple[str, str], tuple[str, str], tuple[str, str]]


MODEL_TIER_ORDER = (ModelTier.FAST, ModelTier.DEFAULT, ModelTier.REASONING)

# These are defaults, not a claim about current provider availability. Deployments
# should set MODEL_* overrides for the models enabled on their provider account.
MAPPINGS: dict[str, ModelTierMapping] = {
    "openai": ModelTierMapping(
        provider="openai",
        names=("gpt-5-mini", "gpt-5", "gpt-5"),
        pricing=(("0.25", "2.00"), ("1.25", "10.00"), ("1.25", "10.00")),
    ),
    "anthropic": ModelTierMapping(
        provider="anthropic",
        names=("claude-haiku-4-5", "claude-sonnet-4-5", "claude-opus-4-5"),
        pricing=(("1.00", "5.00"), ("3.00", "15.00"), ("15.00", "75.00")),
    ),
    "deepseek": ModelTierMapping(
        provider="deepseek",
        names=("deepseek-flash", "deepseek-v4-pro", "deepseek-v4-pro"),
        # Use peak prices so an estimate never understates provider cost.
        pricing=(("0.30", "1.20"), ("1.32", "3.96"), ("1.32", "3.96")),
    ),
}


def resolve_model_tier(tier: ModelTier | str, settings: Settings) -> ModelProfile:
    """Resolve a tier through the single centralized provider mapping."""

    resolved_tier = ModelTier(tier)
    mapping = MAPPINGS.get(settings.llm_provider)
    if mapping is None:
        raise ValueError(f"unsupported llm provider: {settings.llm_provider}")
    index = MODEL_TIER_ORDER.index(resolved_tier)
    overrides = {
        ModelTier.FAST: settings.llm_fast_model,
        ModelTier.DEFAULT: settings.llm_default_model,
        ModelTier.REASONING: settings.llm_reasoning_model,
    }
    name = overrides[resolved_tier].strip() or mapping.names[index]
    input_price, output_price = mapping.pricing[index]
    return ModelProfile(
        tier=resolved_tier,
        provider=mapping.provider,
        name=name,
        input_usd_per_million=Decimal(input_price),
        output_usd_per_million=Decimal(output_price),
    )


def estimate_cost_usd(profile: ModelProfile, input_tokens: int, output_tokens: int) -> Decimal:
    """Calculate a conservative per-call cost from centralized pricing metadata."""

    million = Decimal(1_000_000)
    return (
        Decimal(input_tokens) * profile.input_usd_per_million
        + Decimal(output_tokens) * profile.output_usd_per_million
    ) / million
