from __future__ import annotations

from backend.storage.execution_ledger import ExecutionLedger
from backend.storage.task_store import TaskStore


def _task(task_id: str, execution_id: str) -> dict:
    return {
        "id": task_id,
        "prompt": "run",
        "model": "test",
        "status": "running",
        "created_at": 1.0,
        "started_at": 2.0,
        "completed_at": None,
        "result": None,
        "error": None,
        "metadata": {"execution_id": execution_id, "command": "mission.execute"},
    }


def test_orphan_failure_is_atomic_and_fenced(tmp_path):
    db = tmp_path / "tasks.db"
    store = TaskStore(db)
    ledger = ExecutionLedger(db)
    store.create(_task("task-1", "exec-1"))
    ledger.begin("task-1", "worker-1", execution_id="exec-1")

    assert ledger.fail_orphaned_if_current(
        "task-1",
        "exec-1",
        error="orphaned",
        metadata={"execution_id": "exec-1", "recovery_required": True},
        now=10.0,
    ) is True
    assert store.get("task-1")["status"] == "failed"
    assert ledger.get("exec-1")["state"] == "ambiguous"


def test_orphan_failure_cannot_clobber_newer_execution(tmp_path):
    db = tmp_path / "tasks.db"
    store = TaskStore(db)
    ledger = ExecutionLedger(db)
    store.create(_task("task-1", "exec-1"))
    ledger.begin("task-1", "worker-1", execution_id="exec-1")

    ledger.begin("task-1", "worker-2", execution_id="exec-2", parent_execution_id="exec-1")
    store.update("task-1", metadata={"execution_id": "exec-2", "command": "mission.execute"})

    assert ledger.fail_orphaned_if_current(
        "task-1",
        "exec-1",
        error="stale recovery",
        metadata={"execution_id": "exec-1", "recovery_required": True},
        now=10.0,
    ) is False
    assert store.get("task-1")["status"] == "running"
    assert ledger.get("exec-1")["state"] == "superseded"
    assert ledger.get("exec-2")["state"] == "running"
