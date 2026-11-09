"""带版本与变量校验的安全 Markdown 提示词加载器。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

METADATA_PATTERN = re.compile(
    r"\A<!--\s*\n?(?P<body>.*?)\n?-->\s*",
    re.DOTALL,
)
VERSION_PATTERN = re.compile(r"(?im)^\s*version\s*:\s*([A-Za-z0-9._-]+)\s*$")
CHANGE_PATTERN = re.compile(r"(?im)^\s*change\s*:\s*(.+?)\s*$")
VARIABLE_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class PromptError(ValueError):
    """稳定的提示词加载或渲染失败。"""


@dataclass(frozen=True, slots=True)
class Prompt:
    """经过校验的提示词模板及其元数据。"""

    name: str
    version: str
    change: str
    body: str
    variables: frozenset[str]

    def render(self, **values: str) -> str:
        """仅渲染已声明的变量,并拒绝缺失或意外的值。"""

        supplied = set(values)
        missing = self.variables - supplied
        unexpected = supplied - self.variables
        if missing:
            raise PromptError(f"missing prompt variables: {', '.join(sorted(missing))}")
        if unexpected:
            raise PromptError(f"unexpected prompt variables: {', '.join(sorted(unexpected))}")
        if any(not isinstance(value, str) for value in values.values()):
            raise PromptError("prompt variables must be strings")

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return values[key]

        return VARIABLE_PATTERN.sub(replace, self.body)


class PromptLoader:
    """仅从受信任根目录下读取提示词。"""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    def load(self, name: str) -> Prompt:
        """通过安全的逻辑名称加载并校验提示词。"""

        if not NAME_PATTERN.fullmatch(name):
            raise PromptError("prompt name contains unsupported characters")
        path = (self._root / f"{name}.md").resolve()
        if path.parent != self._root:
            raise PromptError("prompt path escapes the prompt root")
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise PromptError(f"prompt not found: {name}") from exc
        match = METADATA_PATTERN.match(raw)
        if match is None:
            raise PromptError("prompt must start with a metadata comment")
        metadata = match.group("body")
        version_match = VERSION_PATTERN.search(metadata)
        change_match = CHANGE_PATTERN.search(metadata)
        if version_match is None:
            raise PromptError("prompt metadata requires version")
        if change_match is None:
            raise PromptError("prompt metadata requires change")
        body = raw[match.end() :].strip()
        if not body:
            raise PromptError("prompt body must not be empty")
        return Prompt(
            name=name,
            version=version_match.group(1),
            change=change_match.group(1),
            body=body,
            variables=frozenset(VARIABLE_PATTERN.findall(body)),
        )
