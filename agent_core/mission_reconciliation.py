"""Deterministic reconciliation between the TaskStore and durable mission state."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from agent_core.mission_memory import MissionMemory, MissionMemoryStore
from backend.storage.task_store import TaskStore


@dataclass(frozen=True)
class ReconciliationResult:
    task_id: str
    action: str
    task_status: str
    mission_status: str | None
    converged: bool
    safe: bool
    reason: str

    def snapshot(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "action": self.action,
            "task_status": self.task_status,
            "mission_status": self.mission_status,
            "converged": self.converged,
            "safe": self.safe,
            "reason": self.reason,
        }


class MissionReconciler:
    """Converge task and mission state without treating unverified work as success."""

    PROFESSIONAL_COMMAND = "mission.execute"

    def __init__(self, task_store: TaskStore, memory_store: MissionMemoryStore) -> None:
        self.task_store = task_store
        self.memory_store = memory_store

    @staticmethod
    def _is_verified_success(memory: MissionMemory) -> bool:
        execution = memory.last_execution if isinstance(memory.last_execution, dict) else {}
        acceptance = execution.get("acceptance") if isinstance(execution.get("acceptance"), dict) else {}
        evidence = memory.execution_evidence if isinstance(memory.execution_evidence, dict) else {}
        return (
            memory.status == "completed"
            and execution.get("verified") is True
            and acceptance.get("accepted") is True
            and isinstance(evidence, dict)
            and bool(evidence)
        )

    @staticmethod
    def _is_professional(task: dict[str, Any]) -> bool:
        return str(task.get("metadata", {}).get("command", "")).strip().lower() == MissionReconciler.PROFESSIONAL_COMMAND

    def reconcile(self, task_id: str) -> ReconciliationResult:
        task = self.task_store.get(task_id)
        if task is None:
            raise KeyError(task_id)
        task_status = str(task["status"])
        if not self._is_professional(task):
            return ReconciliationResult(task_id, "ignored", task_status, None, True, True, "not a professional mission task")

        memory = self.memory_store.load(task_id)
        if memory is None:
            if task_status == "queued":
                memory = MissionMemory(task_id, task["prompt"])
                self.memory_store.save(memory)
                return ReconciliationResult(task_id, "mission_created", task_status, memory.status, False, True, "queued professional task had no durable mission state")
            if task_status == "running":
                failed = self.task_store.update(
                    task_id,
                    status="failed",
                    error="Mission state missing while task was running; execution is not safe to replay automatically.",
                )
                return ReconciliationResult(task_id, "task_failed_missing_mission", failed["status"], None, False, True, "running task has no durable mission identity")
            return ReconciliationResult(task_id, "mission_missing_terminal_task", task_status, None, False, True, "terminal task has no durable mission state; no success inferred")

        mission_status = memory.status
        if task_status == "completed" and mission_status == "completed" and self._is_verified_success(memory):
            return ReconciliationResult(task_id, "converged", task_status, mission_status, True, True, "both stores contain verified terminal success")

        if mission_status == "completed" and self._is_verified_success(memory) and task_status != "completed":
            execution = dict(memory.last_execution)
            updated = self.task_store.update(
                task_id,
                status="completed",
                result=execution,
                error=None,
                completed_at=time.time(),
            )
            return ReconciliationResult(task_id, "task_completed_from_verified_mission", updated["status"], mission_status, True, True, "durable mission has independently verified acceptance")

        if mission_status == "cancelled":
            if task_status in {"queued", "running"}:
                updated = self.task_store.cancel(task_id, reason="Mission is durably cancelled; reconciliation prevented replay.")
                return ReconciliationResult(task_id, "task_cancelled_from_mission", updated["status"], mission_status, True, True, "mission cancellation is terminal and safe to propagate")
            if task_status == "cancelled":
                return ReconciliationResult(task_id, "converged_cancelled", task_status, mission_status, True, True, "both stores are cancelled")
            return ReconciliationResult(task_id, "terminal_conflict", task_status, mission_status, False, False, "completed or failed task conflicts with durable mission cancellation")

        if mission_status in {"blocked", "interrupted"} and task_status in {"queued", "running"}:
            updated = self.task_store.update(
                task_id,
                status="failed",
                error=f"Mission is {mission_status}; automatic replay is blocked until explicit recovery.",
            )
            return ReconciliationResult(task_id, "task_blocked_for_recovery", updated["status"], mission_status, False, True, "unverified mission state cannot be replayed automatically")

        if mission_status == "running" and task_status == "queued":
            updated = self.task_store.update(task_id, status="running", started_at=time.time())
            return ReconciliationResult(task_id, "task_resumed_to_running", updated["status"], mission_status, True, True, "durable mission is actively running")

        if mission_status == "pending" and task_status == "running":
            updated = self.task_store.update(
                task_id,
                status="failed",
                error="Task was running while its durable mission remained pending; automatic replay is unsafe.",
            )
            return ReconciliationResult(task_id, "task_failed_pending_mission", updated["status"], mission_status, False, True, "execution identity does not prove that mission execution started")

        if task_status == "cancelled" and mission_status in {"pending", "running", "blocked", "interrupted"}:
            try:
                memory.transition("cancelled")
            except ValueError:
                return ReconciliationResult(task_id, "mission_cancel_conflict", task_status, mission_status, False, False, "mission cannot transition safely to cancelled")
            self.memory_store.save(memory)
            return ReconciliationResult(task_id, "mission_cancelled_from_task", task_status, "cancelled", True, True, "durable mission cancellation follows terminal task cancellation")

        return ReconciliationResult(task_id, "no_safe_convergence", task_status, mission_status, False, True, "state mismatch requires explicit recovery policy")

    def reconcile_many(self, *, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        return [self.reconcile(task["id"]).snapshot() for task in self.task_store.list(limit=limit, status=status)]
