"""Task command router built on the canonical command registry."""

from __future__ import annotations

from typing import Any

from task_engine.contracts import TaskRequest
from task_engine.registry import CommandRegistry


DEFAULT_COMMAND = "agent.execute"
COMMAND_METADATA_KEY = "command"


class TaskRouter:
    """Resolve a task command and dispatch it to its registered handler."""

    def __init__(self, registry: CommandRegistry | None = None) -> None:
        self.registry = registry or CommandRegistry()

    def command_for(self, task: TaskRequest) -> str:
        command = task.metadata.get(COMMAND_METADATA_KEY, DEFAULT_COMMAND)
        if not isinstance(command, str) or not command.strip():
            raise ValueError("Task command cannot be empty.")
        return command.strip().lower()

    def route(self, task: TaskRequest, **context: Any) -> Any:
        command = self.command_for(task)
        handler = self.registry.resolve(command)
        return handler(task, **context)
