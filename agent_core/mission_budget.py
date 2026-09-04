"""Deterministic resource governance for long-running autonomous missions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from time import monotonic
from typing import Any


@dataclass(frozen=True)
class MissionBudget:
    """Hard mission-wide ceilings; model output cannot increase them."""

    max_steps: int = 448
    max_tool_calls: int = 448
    max_output_chars: int = 2_097_152
    max_runtime_seconds: float = 1_800.0
    max_recovery_attempts: int = 6
    max_tasks: int = 128
    per_execution_steps: int = 64

    def __post_init__(self) -> None:
        if any(value < 1 for value in (self.max_steps, self.max_tool_calls, self.max_output_chars, self.max_recovery_attempts, self.max_tasks, self.per_execution_steps)):
            raise ValueError("Mission budgets must be positive")
        if self.max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")


class MissionBudgetState:
    """Track measured mission consumption and expose only deterministic remaining limits."""

    def __init__(self, budget: MissionBudget, *, started_at: float | None = None) -> None:
        self.budget = budget
        self.started_at = monotonic() if started_at is None else float(started_at)
        self.steps = 0
        self.tool_calls = 0
        self.output_chars = 0
        self.recovery_attempts = 0
        self.tasks_started = 0

    def elapsed_seconds(self) -> float:
        return max(0.0, monotonic() - self.started_at)

    def remaining(self) -> dict[str, Any]:
        return {
            "steps": max(0, self.budget.max_steps - self.steps),
            "tool_calls": max(0, self.budget.max_tool_calls - self.tool_calls),
            "output_chars": max(0, self.budget.max_output_chars - self.output_chars),
            "runtime_seconds": max(0.0, self.budget.max_runtime_seconds - self.elapsed_seconds()),
            "recovery_attempts": max(0, self.budget.max_recovery_attempts - self.recovery_attempts),
            "tasks": max(0, self.budget.max_tasks - self.tasks_started),
        }

    def reason(self) -> str | None:
        if self.steps >= self.budget.max_steps:
            return "max_steps"
        if self.tool_calls >= self.budget.max_tool_calls:
            return "max_tool_calls"
        if self.output_chars >= self.budget.max_output_chars:
            return "max_output_chars"
        if self.elapsed_seconds() >= self.budget.max_runtime_seconds:
            return "max_runtime_seconds"
        if self.recovery_attempts >= self.budget.max_recovery_attempts:
            return "max_recovery_attempts"
        if self.tasks_started >= self.budget.max_tasks:
            return "max_tasks"
        return None

    def before_task(self) -> str | None:
        reason = self.reason()
        if reason:
            return reason
        self.tasks_started += 1
        return None

    def execution_limits(self) -> dict[str, Any]:
        remaining = self.remaining()
        reason = self.reason()
        if reason:
            raise RuntimeError(f"Mission budget exhausted: {reason}")
        return {
            "max_agent_steps": min(self.budget.per_execution_steps, remaining["steps"], remaining["tool_calls"]),
            "timeout_seconds": max(1, int(remaining["runtime_seconds"])),
            "max_output_chars": min(self.budget.max_output_chars, remaining["output_chars"]),
        }

    def record_execution(self, evidence: dict[str, Any]) -> None:
        self.steps += max(0, int(evidence.get("step_count", 0)))
        self.tool_calls += max(0, int(evidence.get("tool_calls", 0)))
        self.output_chars += max(0, int(evidence.get("output_chars", 0)))

    def record_recovery(self) -> None:
        self.recovery_attempts += 1

    def snapshot(self) -> dict[str, Any]:
        payload = asdict(self.budget)
        payload.update({
            "consumed_steps": self.steps,
            "consumed_tool_calls": self.tool_calls,
            "consumed_output_chars": self.output_chars,
            "consumed_recovery_attempts": self.recovery_attempts,
            "tasks_started": self.tasks_started,
            "started_at": self.started_at,
            "elapsed_seconds": self.elapsed_seconds(),
            "remaining": self.remaining(),
            "exhausted_by": self.reason(),
        })
        return payload
