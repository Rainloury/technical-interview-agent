"""Contract tests for the opt-in live provider evaluation."""

import pytest
from app.config import Settings
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
