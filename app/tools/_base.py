"""工具契约、不可信数据信封、截断和错误规范化。"""

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
    """严格工具参数模型的基类。"""

    model_config = ConfigDict(extra="forbid")


class ToolError(Exception):
    """返回给模型的可恢复工具失败。"""

    def __init__(self, error: str, hint: str) -> None:
        super().__init__(error)
        self.error = error
        self.hint = hint


class ToolContract(BaseModel):
    """由注册表消费的版本化声明。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    params: type[ToolParams]
    func: Any
    permission: Literal["read", "write", "external"] = "read"


class Tool(Protocol):
    """所有工具模块共享的形状。"""

    NAME: ClassVar[str]
    DESCRIPTION: ClassVar[str]
    Params: ClassVar[type[ToolParams]]

    async def run(self, params: BaseModel, *, dry_run: bool = True) -> object:
        """执行工具。"""


def tool_schema(params: type[BaseModel]) -> dict[str, Any]:
    """从 Pydantic 参数模型生成 JSON schema。"""

    return params.model_json_schema()


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _summary(value: object) -> list[str]:
    """描述结果形状而不重新注入大负载。"""

    if isinstance(value, dict):
        keys = ", ".join(str(key) for key in list(value)[:8])
        return [f"mapping with {len(value)} keys", f"keys: {keys}"]
    if isinstance(value, list):
        return [f"sequence with {len(value)} items"]
    return [f"value type: {type(value).__name__}"]


def store_large_result(result: object, *, directory: str | Path, ttl_seconds: int) -> str:
    """将大结果私有写入并仅返回其路径。"""

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
    _ = ttl_seconds  # 保留期由后续切片的清理 Worker 强制执行
    return path


def normalize_tool_result(
    result: object,
    *,
    max_chars: int = MAX_TOOL_RESULT_CHARS,
    result_dir: str | Path | None = None,
    ttl_seconds: int = 3600,
) -> object:
    """限制每个工具结果并为大数据保留简洁摘要。"""

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
    """将预期失败转换为模型可见的错误契约。"""

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
    """包装外部内容,使提示可以严格将其视为数据。"""

    return f"<untrusted>\n{content}\n</untrusted>"


def has_dry_run_default(run: Any) -> bool:
    """检查写操作安全约定。"""

    import inspect

    signature = inspect.signature(run)
    parameter = signature.parameters.get("dry_run")
    return parameter is not None and parameter.default is True
