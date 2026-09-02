"""Persistent mission memory primitives for long-running developer agents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MissionMemory:
    """Durable state for a mission, including enough information to resume it."""

    mission_id: str
    objective: str
    architecture: str = ""
    status: str = "pending"
    decisions: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    tests: list[dict[str, Any]] = field(default_factory=list)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    task_attempts: dict[str, int] = field(default_factory=dict)
    last_execution: dict[str, Any] = field(default_factory=dict)

    VALID_STATUSES = {"pending", "running", "completed", "blocked", "cancelled", "interrupted"}
    TERMINAL_STATUSES = {"completed", "cancelled"}

    def __post_init__(self) -> None:
        if not self.mission_id.strip() or not self.objective.strip():
            raise ValueError("mission_id and objective are required")
        if self.status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid mission status: {self.status}")

    def transition(self, status: str) -> None:
        """Apply a durable lifecycle transition without silently reopening terminal missions."""
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid mission status: {status}")
        if self.status in self.TERMINAL_STATUSES and status != self.status:
            raise ValueError(f"Terminal mission cannot transition from {self.status} to {status}")
        self.status = status

    def checkpoint(
        self,
        *,
        step_id: str,
        summary: str,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = {"step_id": step_id, "summary": summary, "evidence": evidence or {}}
        self.checkpoints.append(item)
        return item

    def record_failure(self, step_id: str, error: str) -> None:
        self.failures.append(f"{step_id}: {error}")

    def record_test(self, name: str, passed: bool, details: str = "") -> None:
        self.tests.append({"name": name, "passed": bool(passed), "details": details})

    def record_attempt(self, step_id: str, attempt: int) -> None:
        self.task_attempts[step_id] = max(int(attempt), self.task_attempts.get(step_id, 0))

    def record_execution(self, result: dict[str, Any]) -> None:
        """Keep the last real runtime result for final acceptance and diagnostics."""
        self.last_execution = result

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


class MissionMemoryStore:
    """Adapter around an optional durable store; memory remains usable without one."""

    def __init__(self, store: Any | None = None):
        self.store = store
        self._memory: dict[str, dict[str, Any]] = {}

    def save(self, memory: MissionMemory) -> None:
        payload = memory.snapshot()
        self._memory[memory.mission_id] = payload
        if self.store is not None:
            if hasattr(self.store, "save_mission"):
                self.store.save_mission(memory.mission_id, payload)
            elif hasattr(self.store, "save"):
                self.store.save(memory.mission_id, payload)

    def load(self, mission_id: str) -> MissionMemory | None:
        payload = self._memory.get(mission_id)
        if payload is None and self.store is not None:
            if hasattr(self.store, "load_mission"):
                payload = self.store.load_mission(mission_id)
            elif hasattr(self.store, "load"):
                payload = self.store.load(mission_id)
        if not payload:
            return None
        return MissionMemory(
            mission_id=payload["mission_id"],
            objective=payload["objective"],
            architecture=payload.get("architecture", ""),
            status=payload.get("status", "pending"),
            decisions=list(payload.get("decisions", [])),
            completed=list(payload.get("completed", [])),
            pending=list(payload.get("pending", [])),
            failures=list(payload.get("failures", [])),
            changed_files=list(payload.get("changed_files", [])),
            tests=list(payload.get("tests", [])),
            checkpoints=list(payload.get("checkpoints", [])),
            task_attempts={key: int(value) for key, value in payload.get("task_attempts", {}).items()},
            last_execution=dict(payload.get("last_execution", {})),
        )
