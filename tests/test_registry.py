"""Tool registry duplicate, contract, and execution tests."""

from __future__ import annotations

from typing import Any

import pytest
from app.agent.registry import RegisteredTool, RegistryError, ToolRegistry
from app.tools._base import ToolParams


class Params(ToolParams):
    value: str = "ok"


async def read_tool(params: Params) -> dict[str, str]:
    return {"value": params.value}


async def write_tool(params: Params, *, dry_run: bool = True) -> dict[str, object]:
    return {"value": params.value, "dry_run": dry_run}


def _tool(
    name: str = "read",
    func: Any = read_tool,
    permission: str = "read",
) -> RegisteredTool:
    return RegisteredTool(
        name=name,
        description="Use for a read; do not use for writes.",
        params=Params,
        func=func,
        permission=permission,
    )


def test_registry_registers_and_executes_valid_tool() -> None:
    registry = ToolRegistry([_tool()])

    assert registry.names == ("read",)
    assert registry.schemas()[0]["parameters"]["type"] == "object"


async def test_registry_validates_arguments_and_invokes_tool() -> None:
    registry = ToolRegistry([_tool()])

    result = await registry.execute("read", {"value": "hello"})

    assert result == {"value": "hello"}


def test_registry_rejects_duplicate_name() -> None:
    registry = ToolRegistry([_tool()])

    with pytest.raises(RegistryError, match="duplicate"):
        registry.register(_tool())


def test_registry_rejects_write_tool_without_dry_run_default() -> None:
    async def unsafe_write(params: Params) -> dict[str, str]:
        return {"value": params.value}

    with pytest.raises(RegistryError, match="dry_run"):
        ToolRegistry([_tool(name="unsafe", func=unsafe_write, permission="write")])


def test_registry_rejects_unregistered_tool() -> None:
    registry = ToolRegistry()

    with pytest.raises(RegistryError, match="not registered"):
        registry.get("dynamic.module")
