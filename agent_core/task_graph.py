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
    def __init__(self, tasks: Iterable[GraphTask] = ()):
        self.tasks = {task.task_id: task for task in tasks}
        self._validate()

    def _validate(self) -> None:
        for task in self.tasks.values():
            missing = task.depends_on - self.tasks.keys()
            if missing:
                raise ValueError(f"Task {task.task_id} depends on unknown tasks: {sorted(missing)}")
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

    def ready(self) -> list[GraphTask]:
        return [task for task in self.tasks.values() if task.status == "pending" and all(self.tasks[d].status == "completed" for d in task.depends_on)]

    def mark_completed(self, task_id: str) -> None:
        self.tasks[task_id].status = "completed"

    def mark_blocked(self, task_id: str) -> None:
        self.tasks[task_id].status = "blocked"

    def is_complete(self) -> bool:
        return bool(self.tasks) and all(task.status == "completed" for task in self.tasks.values())
