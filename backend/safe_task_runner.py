"""Production-safe task runner policy for ambiguous worker outcomes."""

from __future__ import annotations

import time

from backend.task_runner import TaskRunner
from task_engine.contracts import TaskStatus


class SafeTaskRunner(TaskRunner):
    """Prevent automatic replay when a worker outcome is execution-ambiguous."""

    @staticmethod
    def _is_ambiguous_worker_error(error: str) -> bool:
        text = str(error or "").lower()
        if text.startswith("worker request timed out"):
            return True
        if text.startswith("worker request failed:"):
            return True
        if text.startswith("worker http 5"):
            return True
        if "already in progress; duplicate execution rejected" in text:
            return True
        return False

    def _fail_or_retry(self, task_id: str, record: dict, error: str) -> None:
        if not self._is_ambiguous_worker_error(error):
            super()._fail_or_retry(task_id, record, error)
            return

        if self.store.is_cancelled(task_id):
            return
        metadata = dict(record.get("metadata", {}))
        metadata.update(
            {
                "execution_ambiguous": True,
                "automatic_retry_suppressed": True,
                "last_error": error,
            }
        )
        self.store.update(
            task_id,
            status=TaskStatus.FAILED.value,
            completed_at=time.time(),
            error=error,
            metadata=metadata,
        )
