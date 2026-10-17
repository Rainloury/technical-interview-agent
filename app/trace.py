"""Request-scoped trace metadata and LLM call records."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LlmTrace:
    """Metadata captured for every LLM invocation."""

    request_id: str
    trace_id: str
    model_tier: str
    model_name: str
    prompt_name: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    retry_count: int
    tool_calls: tuple[str, ...] = ()
    finish_reason: str | None = None
    error_code: str | None = None
    user_id_hash: str | None = None
    resume_task_id: str | None = None
    qa_request_id: str | None = None
    interview_id: str | None = None
    turn_id: str | None = None

    def as_log_fields(self) -> dict[str, Any]:
        """Return only allowlisted trace fields for structured logs."""

        return {
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "model_tier": self.model_tier,
            "model": self.model_name,
            "prompt_name": self.prompt_name,
            "prompt_version": self.prompt_version,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "retry_count": self.retry_count,
            "tool_calls": self.tool_calls,
            "finish_reason": self.finish_reason,
            "error_code": self.error_code,
            "user_id_hash": self.user_id_hash,
            "resume_task_id": self.resume_task_id,
            "qa_request_id": self.qa_request_id,
            "interview_id": self.interview_id,
            "turn_id": self.turn_id,
        }
