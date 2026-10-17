"""Markdown prompt loading, metadata, path, and variable tests."""

from pathlib import Path

import pytest
from app.prompts.loader import PromptError, PromptLoader


def _write_prompt(root: Path, name: str, body: str) -> None:
    (root / f"{name}.md").write_text(body, encoding="utf-8")


def test_prompt_loads_metadata_and_renders_declared_variables(tmp_path: Path) -> None:
    _write_prompt(
        tmp_path,
        "sample",
        """<!--
version: 1.2.3
change: Test the prompt contract.
-->
Task: {{ task }}
Tools: {{tools}}
""",
    )

    prompt = PromptLoader(tmp_path).load("sample")

    assert prompt.version == "1.2.3"
    assert prompt.variables == frozenset({"task", "tools"})
    assert prompt.render(task="demo", tools="none") == "Task: demo\nTools: none"


def test_prompt_requires_version_and_change(tmp_path: Path) -> None:
    _write_prompt(
        tmp_path,
        "bad",
        """<!--
version: 1
-->
body
""",
    )

    with pytest.raises(PromptError, match="change"):
        PromptLoader(tmp_path).load("bad")


def test_prompt_rejects_missing_and_unexpected_variables(tmp_path: Path) -> None:
    _write_prompt(
        tmp_path,
        "vars",
        """<!--
version: 1
change: variable test
-->
{{ required }}
""",
    )
    prompt = PromptLoader(tmp_path).load("vars")

    with pytest.raises(PromptError, match="missing"):
        prompt.render()
    with pytest.raises(PromptError, match="unexpected"):
        prompt.render(required="yes", extra="no")


@pytest.mark.parametrize("name", ["../secret", "nested/name", "bad name", ""])
def test_prompt_name_cannot_escape_root(tmp_path: Path, name: str) -> None:
    with pytest.raises(PromptError):
        PromptLoader(tmp_path).load(name)
