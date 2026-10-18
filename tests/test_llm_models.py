"""Central model tier and cost mapping tests."""

from decimal import Decimal

from app.config import Settings
from app.llm.models import ModelTier, estimate_cost_usd, resolve_model_tier


def test_model_tiers_are_provider_specific_and_centrally_configured() -> None:
    assert Settings().llm_provider == "deepseek"
    openai = Settings(llm_provider="openai")
    anthropic = Settings(llm_provider="anthropic")
    deepseek = Settings(llm_provider="deepseek")
    local = Settings(llm_provider="local")

    assert resolve_model_tier(ModelTier.FAST, openai).name == "gpt-5-mini"
    assert resolve_model_tier("DEFAULT", anthropic).name == "claude-sonnet-4-5"
    assert resolve_model_tier("FAST", deepseek).name == "deepseek-flash"
    assert resolve_model_tier("REASONING", deepseek).name == "deepseek-v4-pro"
    assert resolve_model_tier("FAST", local).name == "local-stub"


def test_environment_overrides_only_the_selected_tier() -> None:
    settings = Settings(
        llm_provider="openai",
        llm_fast_model="fast-deployment",
        llm_default_model="",
    )

    assert resolve_model_tier("FAST", settings).name == "fast-deployment"
    assert resolve_model_tier("DEFAULT", settings).name == "gpt-5"


def test_cost_uses_decimal_pricing_metadata() -> None:
    profile = resolve_model_tier("FAST", Settings(llm_provider="openai"))

    cost = estimate_cost_usd(profile, input_tokens=1_000_000, output_tokens=1_000_000)

    assert cost == Decimal("2.2500")


def test_deepseek_cost_uses_conservative_peak_price() -> None:
    profile = resolve_model_tier("FAST", Settings(llm_provider="deepseek"))

    cost = estimate_cost_usd(profile, input_tokens=1_000_000, output_tokens=1_000_000)

    assert cost == Decimal("1.5000")
