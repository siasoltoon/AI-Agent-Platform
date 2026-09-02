"""Bounded, priority-aware context selection for long-running coding missions."""

from __future__ import annotations

from typing import Any


class MissionContextManager:
    """Build bounded prompts without truncating away mission-critical context."""

    def __init__(self, max_chars: int = 28_000, chunk_chars: int = 16_000):
        if max_chars < 1 or chunk_chars < 1 or chunk_chars > max_chars:
            raise ValueError("Invalid context limits")
        self.max_chars = max_chars
        self.chunk_chars = chunk_chars

    @staticmethod
    def _render(label: str, value: Any) -> str:
        return f"\n[{label}]\n{value}\n"

    def build(
        self,
        *,
        objective: str,
        architecture: str = "",
        active_task: str = "",
        memory: str = "",
        recent_results: list[str] | None = None,
    ) -> str:
        """Keep objective/task first, then preserve the newest operational context."""
        critical = "".join(
            (
                self._render("OBJECTIVE", objective),
                self._render("ACTIVE TASK", active_task),
                self._render("ARCHITECTURE", architecture),
            )
        )
        operational = self._render("MISSION MEMORY", memory) + "".join(
            self._render(f"RECENT RESULT {index + 1}", item)
            for index, item in enumerate(recent_results or [])
        )
        if len(critical) >= self.max_chars:
            return critical[: self.max_chars]
        remaining = self.max_chars - len(critical)
        if len(operational) <= remaining:
            return critical + operational
        return critical + operational[-remaining:]

    def chunks(self, text: str) -> list[str]:
        return [text[index:index + self.chunk_chars] for index in range(0, len(text), self.chunk_chars)] or [""]
