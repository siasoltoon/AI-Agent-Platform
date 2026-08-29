"""Canonical lifecycle rules for durable task execution."""

from __future__ import annotations

from task_engine.contracts import TaskStatus


TERMINAL_STATUSES = frozenset({TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value})

ALLOWED_TRANSITIONS = {
    TaskStatus.QUEUED.value: frozenset({TaskStatus.RUNNING.value, TaskStatus.CANCELLED.value}),
    TaskStatus.RUNNING.value: frozenset({TaskStatus.QUEUED.value, TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value}),
    TaskStatus.COMPLETED.value: frozenset(),
    TaskStatus.FAILED.value: frozenset(),
    TaskStatus.CANCELLED.value: frozenset(),
}


def can_transition(current: str, target: str) -> bool:
    current = str(current).strip().lower()
    target = str(target).strip().lower()
    return current == target or target in ALLOWED_TRANSITIONS.get(current, frozenset())


def validate_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise ValueError(f"Invalid task lifecycle transition: {current} -> {target}")
