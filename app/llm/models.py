"""集中的模型层级、提供商映射与定价元数据。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.config import Settings


class ModelTier(StrEnum):
    """应用代码使用的稳定层级。"""

    FAST = "FAST"
    DEFAULT = "DEFAULT"
    REASONING = "REASONING"


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """一个已解析的模型及其成本元数据。"""

    tier: ModelTier
    provider: str
    name: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal


@dataclass(frozen=True, slots=True)
class ModelTierMapping:
    """可由环境配置覆盖的提供商默认值。"""

    provider: str
    names: tuple[str, str, str]
    pricing: tuple[tuple[str, str], tuple[str, str], tuple[str, str]]


MODEL_TIER_ORDER = (ModelTier.FAST, ModelTier.DEFAULT, ModelTier.REASONING)

# 这些是默认值,并非对当前提供商可用性的声明。部署时
# 应针对其提供商账户上启用的模型设置 MODEL_* 覆盖值。
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
        # 使用峰值价格,确保估算永远不会低估供应商成本。
        pricing=(("0.30", "1.20"), ("1.32", "3.96"), ("1.32", "3.96")),
    ),
    "local": ModelTierMapping(
        provider="local",
        names=("local-stub", "local-stub", "local-stub"),
        pricing=(("0", "0"), ("0", "0"), ("0", "0")),
    ),
}


def resolve_model_tier(tier: ModelTier | str, settings: Settings) -> ModelProfile:
    """通过单一集中式提供商映射解析层级。"""

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


def configured_model_names(settings: Settings) -> tuple[str, ...]:
    """返回显式配置的非空模型名称以供预检。"""

    return tuple(
        value.strip()
        for value in (
            settings.llm_fast_model,
            settings.llm_default_model,
            settings.llm_reasoning_model,
        )
        if value.strip()
    )


def estimate_cost_usd(profile: ModelProfile, input_tokens: int, output_tokens: int) -> Decimal:
    """根据集中式定价元数据计算保守的单次调用成本。"""

    million = Decimal(1_000_000)
    input_cost = Decimal(input_tokens) * profile.input_usd_per_million
    output_cost = Decimal(output_tokens) * profile.output_usd_per_million
    return (input_cost + output_cost) / million
