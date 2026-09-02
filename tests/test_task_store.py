import shutil

import pytest

from task_engine.contracts import TaskStatus
from backend.storage.task_store import TaskStore


def _seed(store, task_id="task-1", status=TaskStatus.QUEUED.value):
    store.create({
        "id": task_id,
        "prompt": "Create hello.txt",
        "model": None,
        "status": status,
        "created_at": 1.0,
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "metadata": {"command": "agent.execute"},
    })


def test_task_store_persists_and_reloads(tmp_path):
    path = tmp_path / "tasks.db"
    store = TaskStore(path)
    _seed(store)
    store.update("task-1", status=TaskStatus.RUNNING.value, started_at=2.0)
    store.update("task-1", status=TaskStatus.COMPLETED.value, result={"ok": True})

    reloaded = TaskStore(path)
    task = reloaded.get("task-1")
    assert task is not None
    assert task["status"] == TaskStatus.COMPLETED.value
    assert task["result"] == {"ok": True}
    assert [event["event_type"] for event in reloaded.events("task-1")] == ["created", "status_changed", "status_changed"]


def test_task_store_lists_newest_first_and_filters(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    _seed(store, "old")
    _seed(store, "new")
    store.update("new", status=TaskStatus.RUNNING.value)
    assert [task["id"] for task in store.list()] == ["new", "old"]
    assert [task["id"] for task in store.list(status="running")] == ["new"]


def test_task_store_cancel_is_terminal_and_idempotent(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    _seed(store)
    cancelled = store.cancel("task-1", reason="user requested stop")
    assert cancelled["status"] == TaskStatus.CANCELLED.value
    assert cancelled["error"] == "user requested stop"
    again = store.cancel("task-1")
    assert again["status"] == TaskStatus.CANCELLED.value
    assert len(store.events("task-1")) == 2


def test_task_store_rejects_invalid_lifecycle_update(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    _seed(store)
    store.update("task-1", status=TaskStatus.RUNNING.value)
    with pytest.raises(ValueError, match="Invalid task lifecycle transition"):
        store.update("task-1", status=TaskStatus.QUEUED.value)


def test_task_store_recovery_is_audited(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    _seed(store)
    store.update("task-1", status=TaskStatus.RUNNING.value)
    assert store.recover_running_tasks() == 1
    assert store.get("task-1")["status"] == TaskStatus.QUEUED.value
    assert store.events("task-1")[-1]["event_type"] == "recovered"


def test_task_store_releases_sqlite_file_handle(tmp_path):
    path = tmp_path / "tasks.db"
    store = TaskStore(path)
    _seed(store)
    store.get("task-1")
    store.list()
    store.events("task-1")
    store.update("task-1", status=TaskStatus.RUNNING.value)
    store.cancel("task-1")
    store.ping()

    shutil.rmtree(tmp_path)
    assert not path.exists()


def test_task_store_resumes_completed_task_with_same_identity(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    _seed(store)
    store.update("task-1", status=TaskStatus.RUNNING.value, started_at=2.0)
    store.update("task-1", status=TaskStatus.COMPLETED.value, completed_at=3.0, result={"ok": True})

    resumed = store.resume_completed("task-1")

    assert resumed["id"] == "task-1"
    assert resumed["status"] == TaskStatus.QUEUED.value
    assert resumed["started_at"] is None
    assert resumed["completed_at"] is None
    assert resumed["error"] is None
    assert resumed["result"] == {"ok": True}
    assert resumed["metadata"]["resume_count"] == 1
    assert resumed["metadata"]["resumed_from_status"] == "completed"
    assert store.events("task-1")[-1]["event_type"] == "manual_resume_queued"


def test_task_store_resume_completed_is_bounded_to_completed_state(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    _seed(store)

    for status in ("queued", "running", "failed", "cancelled"):
        task_id = f"{status}-task"
        _seed(store, task_id, status)
        with pytest.raises(ValueError, match=f"Task is not resumable: {status}"):
            store.resume_completed(task_id)
