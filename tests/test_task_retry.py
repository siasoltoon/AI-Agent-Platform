import pytest

from backend.storage.task_store import TaskStore
from task_engine.contracts import TaskStatus


def _seed_failed(store: TaskStore, task_id: str = "failed-1") -> None:
    store.create({
        "id": task_id,
        "prompt": "Create a production task",
        "model": "qwen2.5-coder:7b",
        "status": TaskStatus.QUEUED.value,
        "created_at": 1.0,
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "metadata": {"command": "agent.execute", "retry_count": 2},
    })
    store.update(task_id, status=TaskStatus.RUNNING.value, started_at=2.0)
    store.update(task_id, status=TaskStatus.FAILED.value, completed_at=3.0, error="worker failed")


def test_retry_failed_requeues_and_audits(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    _seed_failed(store)

    retried = store.retry_failed("failed-1")

    assert retried["status"] == TaskStatus.QUEUED.value
    assert retried["started_at"] is None
    assert retried["completed_at"] is None
    assert retried["result"] is None
    assert retried["error"] is None
    assert retried["metadata"]["retry_count"] == 0
    assert retried["metadata"]["manual_retry_count"] == 1
    assert store.events("failed-1")[-1]["event_type"] == "manual_retry_queued"
    assert store.events("failed-1")[-1]["detail"]["previous_error"] == "worker failed"


def test_retry_failed_rejects_non_failed_tasks(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    store.create({
        "id": "queued-1",
        "prompt": "hello",
        "model": None,
        "status": TaskStatus.QUEUED.value,
        "created_at": 1.0,
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "metadata": {},
    })

    with pytest.raises(ValueError, match="not retryable"):
        store.retry_failed("queued-1")


def test_retry_failed_rejects_missing_task(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    with pytest.raises(KeyError):
        store.retry_failed("missing")
