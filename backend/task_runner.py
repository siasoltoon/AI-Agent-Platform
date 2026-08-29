"""Durable background executor for controller tasks."""

from __future__ import annotations

import os
import threading
import time

from task_engine.contracts import TaskRequest, TaskStatus


class TaskRunner:
    """Run persisted tasks outside the HTTP request lifecycle with cancellation safety."""

    def __init__(self, store, router, *, poll_seconds: float = 0.25) -> None:
        self.store = store
        self.router = router
        self.poll_seconds = max(0.05, float(poll_seconds))
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
            thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            task = self.store.claim_next_queued()
            if task is None:
                self._stop.wait(self.poll_seconds)
                continue
            self._execute(task)

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
        try:
            result = self.router.route(task, task_id=task_id)
            # Cancellation is authoritative. A worker may finish after a cancel request;
            # never turn that cancelled task back into completed.
            if self.store.is_cancelled(task_id):
                return

            current = self.store.get(task_id) or record
            execution_metadata = {"execution_mode": result.get("execution_mode", "agentic")}
            nested = result.get("result")
            if isinstance(nested, dict):
                execution_metadata.update({
                    "steps": nested.get("steps", 1),
                    "orchestration_mode": nested.get("mode", "agentic"),
                })
            self.store.update(
                task_id,
                status=TaskStatus.COMPLETED.value,
                completed_at=time.time(),
                result=result,
                metadata={**current.get("metadata", {}), **execution_metadata},
            )
        except TimeoutError as exc:
            if not self.store.is_cancelled(task_id):
                self.store.update(task_id, status=TaskStatus.FAILED.value, completed_at=time.time(), error=str(exc) or "Task execution timed out.")
        except Exception as exc:
            if not self.store.is_cancelled(task_id):
                self.store.update(task_id, status=TaskStatus.FAILED.value, completed_at=time.time(), error=str(exc) or "Task execution failed.")


DEFAULT_POLL_SECONDS = float(os.getenv("TASK_RUNNER_POLL_SECONDS", "0.25"))
