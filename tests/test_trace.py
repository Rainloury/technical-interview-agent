"""LLM trace contract tests."""

from dataclasses import FrozenInstanceError

import pytest
from app.trace import LlmTrace


def test_trace_contains_required_observability_fields() -> None:
    trace = LlmTrace(
        request_id="req_1",
        trace_id="trace_1",
        model_tier="DEFAULT",
        model_name="model-v1",
        prompt_name="system",
        prompt_version="1",
        input_tokens=10,
        output_tokens=20,
        latency_ms=100,
        retry_count=0,
        tool_calls=("search",),
    )

    fields = trace.as_log_fields()
    assert {
        "model",
        "prompt_version",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "tool_calls",
        "request_id",
    }.issubset(fields)
    assert fields["model"] == "model-v1"
    assert "model_name" not in fields
    with pytest.raises(FrozenInstanceError):
        trace.request_id = "other"  # type: ignore[misc]
