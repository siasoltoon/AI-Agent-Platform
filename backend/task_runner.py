"""Durable background executor for controller tasks."""

from __future__ import annotations

import os
import threading
import time

from task_engine.contracts import TaskRequest, TaskStatus


class TaskRunner:
    """Run persisted tasks outside HTTP with bounded retries and cancellation safety."""

    def __init__(self, store, router, *, poll_seconds: float = 0.25, default_retries: int = 2) -> None:
        self.store = store
        self.router = router
        self.poll_seconds = max(0.05, float(poll_seconds))
        self.default_retries = max(0, min(int(default_retries), 5))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lifecycle_lock = threading.Lock()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        with self._lifecycle_lock:
            if self.running:
                return
            self.store.recover_running_tasks()
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="task-runner", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lifecycle_lock:
            self._stop.set()
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            task = self.store.claim_next_queued()
            if task is None:
                self._stop.wait(self.poll_seconds)
                continue
            self._execute(task)

    @staticmethod
    def _retry_budget(metadata: dict) -> int:
        try:
            value = int(metadata.get("max_retries", 2))
        except (TypeError, ValueError):
            value = 2
        return max(0, min(value, 5))

    @staticmethod
    def _retry_count(metadata: dict) -> int:
        try:
            return max(0, int(metadata.get("retry_count", 0)))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _execution_evidence(result: dict) -> dict | None:
        """Extract the canonical agent evidence through the runtime/worker envelope."""
        candidates = [result]
        nested = result.get("result")
        if isinstance(nested, dict):
            candidates.append(nested)
            nested_result = nested.get("result")
            if isinstance(nested_result, dict):
                candidates.append(nested_result)
        for candidate in candidates:
            evidence = candidate.get("execution_evidence")
            if isinstance(evidence, dict):
                return evidence
        return None

    def _fail_or_retry(self, task_id: str, record: dict, error: str) -> None:
        if self.store.is_cancelled(task_id):
            return
        metadata = dict(record.get("metadata", {}))
        retries = self._retry_count(metadata)
        budget = self._retry_budget(metadata)
        if retries < budget:
            metadata.update({"retry_count": retries + 1, "last_error": error, "retry_at": time.time()})
            self.store.requeue_for_retry(task_id, metadata=metadata, error=error)
            return
        self.store.update(
            task_id,
            status=TaskStatus.FAILED.value,
            completed_at=time.time(),
            error=error,
            metadata={**metadata, "retry_count": retries, "max_retries": budget},
        )

    def _execute(self, record: dict) -> None:
        task_id = record["id"]
        if self.store.is_cancelled(task_id):
            return

        metadata = dict(record.get("metadata", {}))
        task = TaskRequest(
            prompt=record["prompt"],
            model=record.get("model"),
            task_id=task_id,
            timeout_seconds=metadata.get("timeout_seconds"),
            metadata=metadata,
        )
        started = time.time()
        try:
            result = self.router.route(task, task_id=task_id)
            if self.store.is_cancelled(task_id):
                return

            evidence = self._execution_evidence(result) if isinstance(result, dict) else None
            if not isinstance(evidence, dict) or evidence.get("verified") is not True:
                raise RuntimeError("Task execution completed without verified execution evidence.")

            current = self.store.get(task_id) or record
            execution_metadata = {
                "execution_mode": result.get("execution_mode", "agentic"),
                "duration_seconds": round(time.time() - started, 3),
                "retry_count": self._retry_count(current.get("metadata", {})),
                "execution_evidence": evidence,
            }
            nested = result.get("result")
            if isinstance(nested, dict):
                execution_metadata.update({
                    "steps": nested.get("steps", 1),
                    "orchestration_mode": nested.get("mode", "agentic"),
                })
                nested_result = nested.get("result")
                if isinstance(nested_result, dict):
                    execution_metadata["steps"] = nested_result.get("steps", execution_metadata["steps"])
                    execution_metadata["orchestration_mode"] = nested_result.get("mode", execution_metadata["orchestration_mode"])
            self.store.update(
                task_id,
                status=TaskStatus.COMPLETED.value,
                completed_at=time.time(),
                result=result,
                error=None,
                metadata={**current.get("metadata", {}), **execution_metadata},
            )
        except TimeoutError as exc:
            self._fail_or_retry(task_id, record, str(exc) or "Task execution timed out.")
        except Exception as exc:
            self._fail_or_retry(task_id, record, str(exc) or "Task execution failed.")


DEFAULT_POLL_SECONDS = float(os.getenv("TASK_RUNNER_POLL_SECONDS", "0.25"))
DEFAULT_TASK_RETRIES = max(0, min(int(os.getenv("TASK_RUNNER_MAX_RETRIES", "2")), 5))
