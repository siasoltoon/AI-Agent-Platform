"""Dependency-aware task graph for large autonomous missions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class GraphTask:
    task_id: str
    title: str
    objective: str
    depends_on: set[str] = field(default_factory=set)
    status: str = "pending"
    attempts: int = 0


class TaskGraph:
    """Bounded, dependency-aware state machine for autonomous missions."""

    MAX_TASKS = 128
    TERMINAL_STATUSES = {"completed", "blocked"}

    def __init__(self, tasks: Iterable[GraphTask] = ()):
        self.tasks = {task.task_id: task for task in tasks}
        if len(self.tasks) > self.MAX_TASKS:
            raise ValueError(f"Task graph cannot contain more than {self.MAX_TASKS} tasks")
        self._validate()

    def _validate(self) -> None:
        for task in self.tasks.values():
            if not task.task_id.strip() or not task.title.strip() or not task.objective.strip():
                raise ValueError("Every graph task requires task_id, title, and objective")
            missing = task.depends_on - self.tasks.keys()
            if missing:
                raise ValueError(f"Task {task.task_id} depends on unknown tasks: {sorted(missing)}")
            if task.status not in {"pending", "completed", "blocked"}:
                raise ValueError(f"Task {task.task_id} has invalid status: {task.status}")
            if task.attempts < 0:
                raise ValueError(f"Task {task.task_id} cannot have negative attempts")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError("Task graph contains a dependency cycle")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dep in self.tasks[task_id].depends_on:
                visit(dep)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in self.tasks:
            visit(task_id)

    def add_task(self, task: GraphTask) -> None:
        """Add one task atomically and revalidate dependency/cycle invariants."""
        if task.task_id in self.tasks:
            raise ValueError(f"Task already exists: {task.task_id}")
        if len(self.tasks) >= self.MAX_TASKS:
            raise ValueError(f"Task graph cannot contain more than {self.MAX_TASKS} tasks")
        self.tasks[task.task_id] = task
        try:
            self._validate()
        except Exception:
            del self.tasks[task.task_id]
            raise

    def add_dependency(self, task_id: str, dependency_id: str) -> None:
        """Add a dependency while preserving graph validity."""
        if task_id not in self.tasks or dependency_id not in self.tasks:
            raise KeyError(f"Unknown task dependency: {task_id} <- {dependency_id}")
        if task_id == dependency_id:
            raise ValueError("A task cannot depend on itself")
        task = self.tasks[task_id]
        if dependency_id in task.depends_on:
            return
        task.depends_on.add(dependency_id)
        try:
            self._validate()
        except Exception:
            task.depends_on.remove(dependency_id)
            raise

    def ready(self) -> list[GraphTask]:
        return [
            task
            for task in self.tasks.values()
            if task.status == "pending"
            and all(self.tasks[d].status == "completed" for d in task.depends_on)
        ]

    def mark_completed(self, task_id: str) -> None:
        if task_id not in self.tasks:
            raise KeyError(task_id)
        if self.tasks[task_id].status == "blocked":
            raise ValueError(f"Blocked task cannot be completed without being reset: {task_id}")
        self.tasks[task_id].status = "completed"

    def mark_pending(self, task_id: str) -> None:
        if task_id not in self.tasks:
            raise KeyError(task_id)
        self.tasks[task_id].status = "pending"

    def mark_blocked(self, task_id: str) -> None:
        if task_id not in self.tasks:
            raise KeyError(task_id)
        self.tasks[task_id].status = "blocked"

    def is_complete(self) -> bool:
        return bool(self.tasks) and all(task.status == "completed" for task in self.tasks.values())
