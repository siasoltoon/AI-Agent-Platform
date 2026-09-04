"""Persistent mission memory primitives for long-running developer agents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MissionMemory:
    """Durable state for a mission, including enough information to resume it safely."""

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
    execution_evidence: dict[str, Any] = field(default_factory=dict)
    mission_budget: dict[str, Any] = field(default_factory=dict)
    active_task: str = ""
    active_execution_id: str = ""
    checkpoint_sequence: int = 0

    VALID_STATUSES = {"pending", "running", "completed", "blocked", "cancelled", "interrupted"}
    TERMINAL_STATUSES = {"completed", "cancelled"}
    ALLOWED_TRANSITIONS = {
        "pending": {"running", "cancelled", "interrupted", "blocked"},
        "running": {"completed", "blocked", "cancelled", "interrupted"},
        "interrupted": {"running", "cancelled"},
        "blocked": {"running", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    }

    def __post_init__(self) -> None:
        if not self.mission_id.strip() or not self.objective.strip():
            raise ValueError("mission_id and objective are required")
        if self.status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid mission status: {self.status}")
        self.checkpoint_sequence = max(0, int(self.checkpoint_sequence))

    def transition(self, status: str) -> None:
        """Apply an explicit lifecycle transition and reject invalid state jumps."""
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid mission status: {status}")
        if status == self.status:
            return
        if status not in self.ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"Invalid mission transition: {self.status} -> {status}")
        self.status = status

    def checkpoint(self, *, step_id: str, summary: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        self.checkpoint_sequence += 1
        item = {"sequence": self.checkpoint_sequence, "step_id": step_id, "summary": summary, "evidence": evidence or {}}
        self.checkpoints.append(item)
        return item

    def begin_execution(self, task_id: str, execution_id: str) -> None:
        """Persist the exact execution being attempted before external side effects occur."""
        if not task_id.strip() or not execution_id.strip():
            raise ValueError("task_id and execution_id are required")
        self.active_task = task_id
        self.active_execution_id = execution_id

    def commit_execution(self, *, task_id: str, execution_id: str, result: dict[str, Any]) -> None:
        """Record a verified execution before graph state is advanced."""
        if self.active_task != task_id or self.active_execution_id != execution_id:
            raise ValueError("Execution checkpoint does not match the active execution")
        self.record_execution(result)
        self.checkpoint(step_id=task_id, summary="verified execution committed; safe to advance task graph", evidence={"execution_id": execution_id, "verified": True})

    def clear_execution(self) -> None:
        self.active_task = ""
        self.active_execution_id = ""

    def record_failure(self, step_id: str, error: str) -> None:
        self.failures.append(f"{step_id}: {error}")

    def record_test(self, name: str, passed: bool, details: str = "") -> None:
        self.tests.append({"name": name, "passed": bool(passed), "details": details})

    def record_attempt(self, step_id: str, attempt: int) -> None:
        self.task_attempts[step_id] = max(int(attempt), self.task_attempts.get(step_id, 0))

    def record_execution(self, result: dict[str, Any]) -> None:
        snapshot = dict(result)
        snapshot.setdefault("mission_objective", self.objective)
        self.last_execution = snapshot
        evidence = snapshot.get("execution_evidence")
        if isinstance(evidence, dict):
            self.execution_evidence = dict(evidence)

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
            execution_evidence=dict(payload.get("execution_evidence", {})),
            mission_budget=dict(payload.get("mission_budget", {})),
            active_task=str(payload.get("active_task", "")),
            active_execution_id=str(payload.get("active_execution_id", "")),
            checkpoint_sequence=int(payload.get("checkpoint_sequence", 0)),
        )
