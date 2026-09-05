"""Production-safe task runner policy for ambiguous worker outcomes."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid

from backend.recovery_sweep import RecoverySweep
from backend.storage.execution_ledger import ExecutionLedger
from backend.storage.worker_lease_store import WorkerLeaseStore
from backend.task_runner import TaskRunner
from task_engine.contracts import TaskStatus


class SafeTaskRunner(TaskRunner):
    """Prevent automatic replay when a worker outcome is execution-ambiguous."""

    def __init__(self, store, router, *, poll_seconds: float = 0.25, default_retries: int = 5, shutdown_timeout_seconds: float = 5.0, lease_store: WorkerLeaseStore | None = None, recovery_sweep: RecoverySweep | None = None, execution_ledger: ExecutionLedger | None = None, worker_id: str | None = None, lease_ttl_seconds: float | None = None, heartbeat_seconds: float | None = None) -> None:
        super().__init__(store, router, poll_seconds=poll_seconds, default_retries=default_retries, shutdown_timeout_seconds=shutdown_timeout_seconds)
        store_path = getattr(store, "path", "data/tasks.db")
        self.lease_store = lease_store or WorkerLeaseStore(store_path)
        self.execution_ledger = execution_ledger or ExecutionLedger(store_path)
        self.recovery_sweep = recovery_sweep
        self.worker_id = str(worker_id or os.getenv("TASK_RUNNER_WORKER_ID") or f"controller-{uuid.uuid4()}")
        self.lease_ttl_seconds = max(5.0, float(lease_ttl_seconds or os.getenv("TASK_LEASE_TTL_SECONDS", "30")))
        default_heartbeat = min(10.0, self.lease_ttl_seconds / 3.0)
        self.heartbeat_seconds = max(1.0, min(float(heartbeat_seconds or os.getenv("TASK_HEARTBEAT_SECONDS", str(default_heartbeat))), self.lease_ttl_seconds / 2.0))

    def start(self) -> None:
        """Start without blindly requeueing executions that may have side effects."""
        with self._lifecycle_lock:
            if self.running:
                return
            if self.recovery_sweep is not None:
                self.recovery_sweep.sweep(limit=500)
            else:
                RecoverySweep(self.store, self.lease_store, execution_ledger=self.execution_ledger).sweep(limit=500)
            self._stop.clear(); self._shutdown_timed_out = False
            self._thread = threading.Thread(target=self._run, name="task-runner", daemon=True); self._thread.start()

    @staticmethod
    def _is_ambiguous_worker_error(error: str) -> bool:
        text = str(error or "").lower().strip()
        ambiguous_prefixes = ("worker request timed out", "worker request failed:", "worker request cancelled:", "worker http 408:", "worker http 429:", "worker http 5", "worker returned a non-json response.", "worker returned an invalid json response object.", "execution lease lost", "execution lease could not be acquired", "execution fence rejected")
        return text.startswith(ambiguous_prefixes) or "already in progress; duplicate execution rejected" in text

    def _fail_or_retry(self, task_id: str, record: dict, error: str) -> None:
        if not self._is_ambiguous_worker_error(error):
            super()._fail_or_retry(task_id, record, error); return
        if self.store.is_cancelled(task_id): return
        current = self.store.get(task_id) or record
        if current.get("status") not in {TaskStatus.RUNNING.value, TaskStatus.QUEUED.value}: return
        metadata = dict(current.get("metadata", {}))
        execution_id = metadata.get("execution_id")
        metadata.update({"execution_ambiguous": True, "automatic_retry_suppressed": True, "recovery_required": True, "last_error": error})
        if execution_id and current.get("status") == TaskStatus.RUNNING.value:
            # A running task with an execution identity must terminalize through
            # the same durable fence. Never fall back to an unfenced TaskStore
            # update after a fence rejection, because that could clobber a newer
            # execution attempt.
            self.execution_ledger.fail_orphaned_if_current(task_id, str(execution_id), error=error, metadata=metadata)
            return
        if execution_id:
            self.execution_ledger.transition(execution_id, "ambiguous", error=error)
        self.store.update(task_id, status=TaskStatus.FAILED.value, completed_at=time.time(), error=error, metadata=metadata)

    def _execute(self, record: dict) -> None:
        """Execute only while this controller owns a renewable durable lease."""
        task_id = record["id"]; execution_id = str(uuid.uuid4()); original_store = self.store
        if not self.lease_store.acquire(task_id, self.worker_id, execution_id, ttl_seconds=self.lease_ttl_seconds):
            self._fail_or_retry(task_id, record, "Execution lease could not be acquired; another execution may still own this task."); return
        attempt = self.execution_ledger.begin(task_id, self.worker_id, execution_id=execution_id, parent_execution_id=(record.get("metadata") or {}).get("execution_id"), idempotency_key=(record.get("metadata") or {}).get("idempotency_key"))
        if attempt.get("execution_id") != execution_id:
            self.lease_store.release(task_id, self.worker_id, execution_id); state = str(attempt.get("state", "unknown"))
            if state == "committed":
                stored_result = attempt.get("result_json")
                if stored_result:
                    current = original_store.get(task_id) or record; metadata = dict(current.get("metadata", {})); metadata.update({"execution_id": attempt["execution_id"], "fencing_token": attempt["fencing_token"], "execution_ledger_path": str(self.execution_ledger.path), "idempotent_replay": True})
                    replay_result = json.loads(stored_result)
                    restored = self.execution_ledger.restore_committed_task_if_current(task_id, str(attempt["execution_id"]), int(attempt["fencing_token"]), result=replay_result, metadata=metadata)
                    if restored:
                        return
            self._fail_or_retry(task_id, record, "Execution idempotency request is already owned by another attempt."); return

        fencing_token = int(attempt["fencing_token"]); current = original_store.get(task_id) or record; metadata = dict(current.get("metadata", {}))
        metadata.update({"worker_id": self.worker_id, "execution_id": execution_id, "fencing_token": fencing_token, "attempt_no": int(attempt["attempt_no"]), "lease_ttl_seconds": self.lease_ttl_seconds, "heartbeat_seconds": self.heartbeat_seconds, "execution_ledger_path": str(self.execution_ledger.path)})
        if current.get("status") == TaskStatus.RUNNING.value: original_store.update(task_id, metadata=metadata)
        leased_record = dict(record); leased_record["metadata"] = metadata

        heartbeat_stop = threading.Event(); lease_lost = threading.Event()
        def heartbeat() -> None:
            while not heartbeat_stop.wait(self.heartbeat_seconds):
                try: renewed = self.lease_store.renew(task_id, self.worker_id, execution_id, ttl_seconds=self.lease_ttl_seconds)
                except Exception: renewed = False
                if not renewed:
                    lease_lost.set(); self.execution_ledger.transition(execution_id, "ambiguous", error="Execution lease heartbeat was lost."); return

        original_router = self.router; lease_store = self.lease_store; ledger = self.execution_ledger; worker_id = self.worker_id
        class LeaseCheckedRouter:
            def route(inner_self, task, *, task_id: str):
                result = original_router.route(task, task_id=task_id)
                if lease_lost.is_set() or not lease_store.owns(task_id, worker_id, execution_id): raise RuntimeError("Execution lease lost before durable completion could be trusted.")
                if not ledger.fence_check(task_id, execution_id, fencing_token): raise RuntimeError("Execution fence rejected completion because a newer attempt owns the task.")
                return result

        heartbeat_thread = threading.Thread(target=heartbeat, name=f"task-heartbeat-{task_id}", daemon=True); heartbeat_thread.start(); self.router = LeaseCheckedRouter()
        class FencedStore:
            """Delegate all TaskStore operations except fenced completion."""
            def __getattr__(inner_self, name): return getattr(original_store, name)
            def update(inner_self, update_task_id: str, **changes):
                if update_task_id == task_id and changes.get("status") == TaskStatus.COMPLETED.value:
                    ok = ledger.commit_task_if_current(task_id, execution_id, fencing_token, result=changes.get("result"), metadata=changes.get("metadata", {}))
                    if not ok: raise RuntimeError("Execution fence rejected completion because a newer attempt owns the task.")
                    return original_store.get(task_id)
                return original_store.update(update_task_id, **changes)

        self.store = FencedStore()
        try:
            super()._execute(leased_record)
        finally:
            self.store = original_store; self.router = original_router; heartbeat_stop.set(); heartbeat_thread.join(timeout=max(1.0, self.heartbeat_seconds + 0.5))
            current_attempt = ledger.get(execution_id)
            if current_attempt and current_attempt.get("state") == "running":
                current_task = original_store.get(task_id)
                if current_task and current_task.get("status") == TaskStatus.COMPLETED.value: ledger.transition(execution_id, "committed")
                else: ledger.transition(execution_id, "interrupted", error="Execution ended without a durable completion commit.")
            self.lease_store.release(task_id, self.worker_id, execution_id)


DEFAULT_POLL_SECONDS = float(os.getenv("TASK_RUNNER_POLL_SECONDS", "0.25"))
DEFAULT_TASK_RETRIES = max(0, min(int(os.getenv("TASK_RUNNER_MAX_RETRIES", "5")), 5))
