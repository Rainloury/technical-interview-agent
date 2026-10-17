"""Explicit tool registration with duplicate and contract validation."""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.tools._base import (
    ToolParams,
    has_dry_run_default,
    tool_schema,
)


class RegistryError(ValueError):
    """Invalid or conflicting tool registration."""


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    """One validated tool available to the model."""

    name: str
    description: str
    params: type[ToolParams]
    func: Any
    permission: str = "read"

    @property
    def schema(self) -> dict[str, Any]:
        return tool_schema(self.params)


class ToolRegistry:
    """Explicit, immutable-by-convention set of tools."""

    def __init__(self, tools: Iterable[RegisteredTool] = ()) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        for tool in tools:
            self.register(tool)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def register(self, tool: RegisteredTool) -> None:
        if not tool.name or not tool.name.replace("_", "").isalnum():
            raise RegistryError("tool name must be a non-empty identifier")
        if not tool.description.strip():
            raise RegistryError(f"tool {tool.name} requires a description")
        if tool.name in self._tools:
            raise RegistryError(f"duplicate tool name: {tool.name}")
        if not issubclass(tool.params, BaseModel):
            raise RegistryError(f"tool {tool.name} params must be a Pydantic model")
        if tool.permission not in {"read", "write", "external"}:
            raise RegistryError(f"tool {tool.name} has an invalid permission")
        if not inspect.iscoroutinefunction(tool.func):
            raise RegistryError(f"tool {tool.name} run must be async")
        if tool.permission != "read" and not has_dry_run_default(tool.func):
            raise RegistryError(f"tool {tool.name} must default dry_run=True")
        self._tools[tool.name] = tool

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise RegistryError(f"tool is not registered: {name}") from exc

    def schemas(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.schema,
            }
            for tool in self._tools.values()
        )

    async def execute(
        self,
        name: str,
        arguments: BaseModel | dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> object:
        tool = self.get(name)
        params = (
            arguments
            if isinstance(arguments, tool.params)
            else tool.params.model_validate(arguments)
        )
        if tool.permission == "read":
            return await tool.func(params)
        return await tool.func(params, dry_run=dry_run)
