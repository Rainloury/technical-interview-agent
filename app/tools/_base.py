"""Tool contract, untrusted-data envelope, truncation, and error normalization."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

ParamsT = TypeVar("ParamsT", bound=BaseModel)
MAX_TOOL_RESULT_CHARS = 2000
SUMMARY_LINES = 3


class ToolParams(BaseModel):
    """Base for strict tool parameter models."""

    model_config = ConfigDict(extra="forbid")


class ToolError(Exception):
    """A recoverable tool failure returned to the model."""

    def __init__(self, error: str, hint: str) -> None:
        super().__init__(error)
        self.error = error
        self.hint = hint


class ToolContract(BaseModel):
    """Versioned declaration consumed by the registry."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    params: type[ToolParams]
    func: Any
    permission: Literal["read", "write", "external"] = "read"


class Tool(Protocol):
    """Shape shared by all tool modules."""

    NAME: ClassVar[str]
    DESCRIPTION: ClassVar[str]
    Params: ClassVar[type[ToolParams]]

    async def run(self, params: BaseModel, *, dry_run: bool = True) -> object:
        """Execute the tool."""


def tool_schema(params: type[BaseModel]) -> dict[str, Any]:
    """Generate a JSON schema from the Pydantic parameter model."""

    return params.model_json_schema()


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _summary(value: object) -> list[str]:
    """Describe the result shape without re-injecting a large payload."""

    if isinstance(value, dict):
        keys = ", ".join(str(key) for key in list(value)[:8])
        return [f"mapping with {len(value)} keys", f"keys: {keys}"]
    if isinstance(value, list):
        return [f"sequence with {len(value)} items"]
    return [f"value type: {type(value).__name__}"]


def store_large_result(result: object, *, directory: str | Path, ttl_seconds: int) -> str:
    """Write a large result privately and return only its path."""

    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    target.chmod(0o700)
    handle, path = tempfile.mkstemp(prefix="tool-", suffix=".json", dir=target)
    try:
        with open(handle, "w", encoding="utf-8") as file:
            file.write(_json_text(result))
        Path(path).chmod(0o600)
    except Exception:
        Path(path).unlink(missing_ok=True)
        raise
    _ = ttl_seconds  # retention is enforced by the cleanup worker in a later slice
    return path


def normalize_tool_result(
    result: object,
    *,
    max_chars: int = MAX_TOOL_RESULT_CHARS,
    result_dir: str | Path | None = None,
    ttl_seconds: int = 3600,
) -> object:
    """Bound every tool result and preserve a concise summary for large data."""

    serialized = _json_text(result)
    if len(serialized) <= max_chars:
        return result
    if result_dir is None:
        text = serialized[:max_chars]
        return {
            "truncated": True,
            "original_length": len(serialized),
            "preview": text,
        }
    path = store_large_result(result, directory=result_dir, ttl_seconds=ttl_seconds)
    return {
        "truncated": True,
        "original_length": len(serialized),
        "path": path,
        "summary": _summary(result),
    }


def error_envelope(exc: Exception) -> dict[str, str] | dict[str, object]:
    """Convert expected failures into the model-visible error contract."""

    if isinstance(exc, ToolError):
        return {"ok": False, "error": exc.error, "hint": exc.hint}
    if isinstance(exc, ValidationError):
        return {
            "ok": False,
            "error": "tool parameters are invalid",
            "hint": "correct the parameter values and retry",
        }
    return {
        "ok": False,
        "error": "tool execution failed",
        "hint": "inspect the input and retry with a supported action",
    }


def wrap_untrusted(content: str) -> str:
    """Wrap external content so prompts can treat it strictly as data."""

    return f"<untrusted>\n{content}\n</untrusted>"


def has_dry_run_default(run: Any) -> bool:
    """Check the write-operation safety convention."""

    import inspect

    signature = inspect.signature(run)
    parameter = signature.parameters.get("dry_run")
    return parameter is not None and parameter.default is True
