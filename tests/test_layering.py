"""对已批准依赖方向的静态检查。"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

SERVICES_ALLOWED = (
    "app.config",
    "app.crypto",
    "app.db",
    "app.errors",
    "app.interview_contracts",
    "app.logging",
    "app.qa_contracts",
    "app.resume_contracts",
    "app.resume_processing",
    "app.schemas",
    "app.security",
    "app.storage",
    "app.services",
)

SERVICES_FORBIDDEN = (
    "app.api",
    "app.agent",
    "app.tools",
    "app.llm",
    "app.worker",
)


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


def _imported_names(package: Path) -> set[str]:
    names: set[str] = set()
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names.update(
                    f"{node.module}.{alias.name}"
                    for alias in node.names
                    if alias.name.startswith("_") and alias.name != "__all__"
                )
    return names


def _assert_no_imports(package: Path, forbidden_prefixes: tuple[str, ...]) -> None:
    imports = _imports(package)
    violations = sorted(
        module
        for module in imports
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    )
    assert not violations, f"{package.name} has forbidden imports: {violations}"


def _assert_only_imports(package: Path, allowed_prefixes: tuple[str, ...]) -> None:
    imports = _imports(package)
    violations = sorted(
        module
        for module in imports
        if module.startswith("app.")
        and not any(
            module == prefix or module.startswith(f"{prefix}.") for prefix in allowed_prefixes
        )
    )
    assert not violations, f"{package.name} has unapproved imports: {violations}"


def test_api_does_not_import_agent_internals_or_llm() -> None:
    _assert_no_imports(APP / "api", ("app.agent", "app.llm", "app.tools", "app.worker"))


def test_api_imports_services_for_use_cases() -> None:
    assert "app.services.auth" in _imports(APP / "api")
    assert "app.services.interviews" in _imports(APP / "api")


def test_services_follow_approved_dependency_matrix() -> None:
    services = APP / "services"
    _assert_only_imports(services, SERVICES_ALLOWED)
    _assert_no_imports(services, SERVICES_FORBIDDEN)


def test_services_do_not_import_private_members_from_other_services() -> None:
    violations = sorted(
        name for name in _imported_names(APP / "services") if name.startswith("app.services.")
    )
    assert not violations, f"services has cross-module private imports: {violations}"


def test_services_dependency_check_rejects_forbidden_import() -> None:
    """失败样例: 禁止清单必须能拦住 services 直连 api。"""

    imports = {"app.services.documents", "app.api.v1.documents"}
    violations = sorted(
        module
        for module in imports
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in SERVICES_FORBIDDEN)
    )
    assert violations == ["app.api.v1.documents"]


def test_tools_do_not_import_api_or_agent() -> None:
    _assert_no_imports(APP / "tools", ("app.api", "app.agent"))


def test_llm_does_not_import_business_layers() -> None:
    _assert_no_imports(APP / "llm", ("app.api", "app.agent", "app.tools", "app.prompts"))


def test_agent_does_not_import_api() -> None:
    _assert_no_imports(APP / "agent", ("app.api",))
