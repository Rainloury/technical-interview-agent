"""Static checks for the approved dependency direction."""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _imports(package: Path) -> set[str]:
    modules: set[str] = set()
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
            elif isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
    return modules


def _assert_no_imports(package: Path, forbidden_prefixes: tuple[str, ...]) -> None:
    imports = _imports(package)
    violations = sorted(
        module
        for module in imports
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    )
    assert not violations, f"{package.name} has forbidden imports: {violations}"


def test_api_does_not_import_agent_internals_or_llm() -> None:
    _assert_no_imports(APP / "api", ("app.agent", "app.llm", "app.tools"))


def test_tools_do_not_import_api_or_agent() -> None:
    _assert_no_imports(APP / "tools", ("app.api", "app.agent"))


def test_llm_does_not_import_business_layers() -> None:
    _assert_no_imports(APP / "llm", ("app.api", "app.agent", "app.tools", "app.prompts"))


def test_agent_does_not_import_api() -> None:
    _assert_no_imports(APP / "agent", ("app.api",))
