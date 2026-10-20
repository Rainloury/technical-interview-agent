"""Contract tests for the opt-in live provider evaluation."""

import pytest
from app.config import Settings
from app.llm.client import _chat_completions_root
from app.prompts.loader import PromptLoader
from evals.provider_behavior import run_provider_check


async def test_provider_eval_requires_an_api_key() -> None:
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        await run_provider_check(Settings(app_env="test", llm_api_key=None))


def test_provider_evidence_identifies_every_prompt_used() -> None:
    settings = Settings(app_env="test")
    loader = PromptLoader(settings.prompt_dir)
    system = loader.load("agent_system")
    turn = loader.load("agent_turn")

    assert f"agent_system@{system.version}" in (
        f"agent_system@{system.version}+agent_turn@{turn.version}"
    )
    assert f"agent_turn@{turn.version}" in (
        f"agent_system@{system.version}+agent_turn@{turn.version}"
    )


def test_openai_compatible_endpoint_uses_chat_completions_without_models_preflight() -> None:
    settings = Settings(
        llm_provider="openai",
        llm_base_url="https://copilot.tencent.com/v2/chat/completions",
    )

    assert _chat_completions_root(settings.llm_base_url) == "https://copilot.tencent.com/v2"
