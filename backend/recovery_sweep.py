"""Conservative startup recovery for orphaned task executions."""

from __future__ import annotations

import time
from typing import Any

from agent_core.mission_reconciliation import MissionReconciler
from backend.storage.execution_ledger import ExecutionLedger
from backend.storage.task_store import TaskStore
from backend.storage.worker_lease_store import WorkerLeaseStore


class RecoverySweep:
    """Repair only states that are provably safe; never blindly replay orphaned work."""

    def __init__(
        self,
        task_store: TaskStore,
        lease_store: WorkerLeaseStore,
        reconciler: MissionReconciler | None = None,
        execution_ledger: ExecutionLedger | None = None,
    ) -> None:
        self.task_store = task_store
        self.lease_store = lease_store
        self.reconciler = reconciler
        self.execution_ledger = execution_ledger or ExecutionLedger(task_store.path)

    @staticmethod
    def _professional(task: dict[str, Any]) -> bool:
        return str(task.get("metadata", {}).get("command", "")).strip().lower() == "mission.execute"

    def sweep(self, *, limit: int = 100, now: float | None = None) -> dict[str, Any]:
        limit = max(1, min(int(limit), 500))
        current = time.time() if now is None else float(now)
        stale = self.lease_store.purge_stale(now=current, limit=limit)
        stale_by_task = {lease["task_id"]: lease for lease in stale}
        actions: list[dict[str, Any]] = []

        running = self.task_store.list(limit=limit, status="running")
        for task in running:
            task_id = task["id"]
            lease = self.lease_store.get(task_id)
            if lease is not None and lease["lease_until"] >= current and lease["status"] == "active":
                actions.append({"task_id": task_id, "action": "active_lease_preserved", "safe": True})
                continue

            if self._professional(task) and self.reconciler is not None:
                result = self.reconciler.reconcile(task_id).snapshot()
                actions.append(result)
                refreshed = self.task_store.get(task_id)
                if refreshed is None or refreshed["status"] != "running":
                    continue

            stale_lease = stale_by_task.get(task_id)
            execution_id = stale_lease.get("execution_id") if stale_lease else task.get("metadata", {}).get("execution_id")
            attempt = self.execution_ledger.get(str(execution_id)) if execution_id else None

            metadata = dict(task.get("metadata", {}))
            metadata.update(
                {
                    "recovery_required": True,
                    "automatic_retry_suppressed": True,
                    "orphaned_execution": True,
                    "orphaned_execution_id": execution_id,
                    "orphaned_execution_state": attempt.get("state") if attempt else None,
                    "recovered_at": current,
                }
            )
            if execution_id:
                failed = self.execution_ledger.fail_orphaned_if_current(
                    task_id,
                    str(execution_id),
                    error="Execution owner disappeared or lease expired; automatic replay is unsafe.",
                    metadata=metadata,
                    now=current,
                )
            else:
                failed = False

            if failed:
                actions.append(
                    {
                        "task_id": task_id,
                        "action": "orphaned_execution_failed",
                        "task_status": "failed",
                        "safe": True,
                        "execution_id": execution_id,
                        "execution_state": "ambiguous",
                    }
                )
            else:
                refreshed = self.task_store.get(task_id)
                actions.append(
                    {
                        "task_id": task_id,
                        "action": "orphan_recovery_skipped_stale_fence",
                        "task_status": refreshed["status"] if refreshed else None,
                        "safe": True,
                        "execution_id": execution_id,
                    }
                )

        return {
            "stale_leases": len(stale),
            "running_tasks_examined": len(running),
            "actions": actions,
        }
