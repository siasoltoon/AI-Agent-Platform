"""Command registry for the canonical task execution pipeline."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


TaskHandler = Callable[..., Any]


class CommandRegistry:
    """Maps stable command names to executable task handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, TaskHandler] = {}

    def register(self, command: str, handler: TaskHandler, *, replace: bool = False) -> None:
        name = self._normalize(command)
        if not callable(handler):
            raise TypeError("Command handler must be callable.")
        if name in self._handlers and not replace:
            raise ValueError(f"Command already registered: {name}")
        self._handlers[name] = handler

    def unregister(self, command: str) -> None:
        name = self._normalize(command)
        self._handlers.pop(name, None)

    def resolve(self, command: str) -> TaskHandler:
        name = self._normalize(command)
        try:
            return self._handlers[name]
        except KeyError as exc:
            raise KeyError(f"Unknown command: {name}") from exc

    def has(self, command: str) -> bool:
        return self._normalize(command) in self._handlers

    def commands(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    @staticmethod
    def _normalize(command: str) -> str:
        if not isinstance(command, str):
            raise TypeError("Command must be a string.")
        name = command.strip().lower()
        if not name:
            raise ValueError("Command cannot be empty.")
        return name
