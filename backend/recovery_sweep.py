"""Conservative startup recovery for orphaned task executions."""

from __future__ import annotations

import json
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

    @staticmethod
    def _stored_result(attempt: dict[str, Any]) -> Any:
        raw = attempt.get("result_json")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

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

            # A stale lease is authoritative about the execution identity even
            # when the lease predates ledger persistence. Materialize that
            # identity instead of inventing a different attempt.
            if execution_id is not None and attempt is None:
                current_attempt = self.execution_ledger.current(task_id)
                if current_attempt is None:
                    attempt = self.execution_ledger.begin(
                        task_id,
                        "recovery-sweep",
                        execution_id=str(execution_id),
                        now=current,
                    )
                elif str(current_attempt["execution_id"]) == str(execution_id):
                    attempt = current_attempt
                else:
                    # A newer fenced attempt already exists; do not mutate it.
                    attempt = current_attempt

            # Legacy tasks may predate the execution ledger and have no durable
            # execution identity. Establish a recovery-owned attempt before
            # failing them, so the terminal transition remains ledger-fenced.
            if execution_id is None:
                current_attempt = self.execution_ledger.current(task_id)
                if current_attempt is not None:
                    execution_id = str(current_attempt["execution_id"])
                    attempt = current_attempt
                else:
                    attempt = self.execution_ledger.begin(task_id, "recovery-sweep", now=current)
                    execution_id = str(attempt["execution_id"])

            # If durable execution already committed, reconcile the task from
            # that authoritative result instead of treating it as an orphan.
            # This closes the crash window between ledger commit and task-row
            # publication while preserving fencing against newer attempts.
            if (
                attempt is not None
                and str(attempt.get("state")) == "committed"
                and str(attempt.get("execution_id")) == str(execution_id)
            ):
                stored_result = self._stored_result(attempt)
                if stored_result is not None:
                    metadata = dict(task.get("metadata", {}))
                    metadata.update(
                        {
                            "execution_id": execution_id,
                            "fencing_token": int(attempt["fencing_token"]),
                            "recovery_required": False,
                            "recovered_at": current,
                            "committed_execution_reconciled": True,
                            "execution_ledger_path": str(self.execution_ledger.path),
                        }
                    )
                    restored = self.execution_ledger.restore_committed_task_if_current(
                        task_id,
                        str(execution_id),
                        int(attempt["fencing_token"]),
                        result=stored_result,
                        metadata=metadata,
                        now=current,
                    )
                    if restored:
                        actions.append(
                            {
                                "task_id": task_id,
                                "action": "committed_execution_reconciled",
                                "task_status": "completed",
                                "safe": True,
                                "execution_id": execution_id,
                                "execution_state": "committed",
                            }
                        )
                        continue

            metadata = dict(task.get("metadata", {}))
            metadata.update(
                {
                    "execution_id": execution_id,
                    "recovery_required": True,
                    "automatic_retry_suppressed": True,
                    "orphaned_execution": True,
                    "orphaned_execution_id": execution_id,
                    "orphaned_execution_state": attempt.get("state") if attempt else None,
                    "recovered_at": current,
                }
            )
            failed = self.execution_ledger.fail_orphaned_if_current(
                task_id,
                str(execution_id),
                error="Execution owner disappeared or lease expired; automatic replay is unsafe.",
                metadata=metadata,
                now=current,
            )

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
