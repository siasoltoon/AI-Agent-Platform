"""Bounded context selection for long-running coding missions."""

from __future__ import annotations

from typing import Any


class MissionContextManager:
    def __init__(self, max_chars: int = 28_000, chunk_chars: int = 16_000):
        if max_chars < 1 or chunk_chars < 1 or chunk_chars > max_chars:
            raise ValueError("Invalid context limits")
        self.max_chars = max_chars
        self.chunk_chars = chunk_chars

    @staticmethod
    def _render(label: str, value: Any) -> str:
        return f"\n[{label}]\n{value}\n"

    def build(self, *, objective: str, architecture: str = "", active_task: str = "", memory: str = "", recent_results: list[str] | None = None) -> str:
        sections = [self._render("OBJECTIVE", objective), self._render("ARCHITECTURE", architecture), self._render("ACTIVE TASK", active_task), self._render("MISSION MEMORY", memory)]
        for index, item in enumerate(recent_results or []):
            sections.append(self._render(f"RECENT RESULT {index + 1}", item))
        text = "".join(sections)
        if len(text) <= self.max_chars:
            return text
        return text[-self.max_chars:]

    def chunks(self, text: str) -> list[str]:
        return [text[index:index + self.chunk_chars] for index in range(0, len(text), self.chunk_chars)] or [""]
