"""Production tool registry with stable names, descriptions and safe resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    name: str
    tool: Any
    description: str


class ToolRegistry:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}
        self.specs: dict[str, ToolSpec] = {}

    @staticmethod
    def _normalize(name: str) -> str:
        value = str(name).strip().lower()
        if not value:
            raise ValueError("Tool name cannot be empty.")
        return value

    def register(self, tool: Any, *, description: str = "", replace: bool = False) -> None:
        name = self._normalize(tool.name)
        if name in self.tools and not replace:
            raise ValueError(f"Tool already registered: {name}")
        self.tools[name] = tool
        self.specs[name] = ToolSpec(name=name, tool=tool, description=description)

    def get(self, name: str) -> Any:
        return self.tools.get(self._normalize(name))

    def resolve(self, name: str) -> Any:
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"Unknown tool: {self._normalize(name)}")
        return tool

    def has(self, name: str) -> bool:
        return self._normalize(name) in self.tools

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self.tools))

    def descriptions(self) -> dict[str, str]:
        return {name: spec.description for name, spec in sorted(self.specs.items())}

    def unregister(self, name: str) -> None:
        key = self._normalize(name)
        self.tools.pop(key, None)
        self.specs.pop(key, None)
