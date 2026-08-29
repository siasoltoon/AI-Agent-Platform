from task_engine.contracts import TaskStatus
from backend.storage.task_store import TaskStore


def test_task_store_persists_and_reloads(tmp_path):
    path = tmp_path / "tasks.db"
    store = TaskStore(path)
    store.create(
        {
            "id": "task-1",
            "prompt": "Create a file",
            "model": "test-model",
            "status": TaskStatus.QUEUED.value,
            "created_at": 1.0,
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
            "metadata": {"command": "agent.execute"},
        }
    )
    store.update("task-1", status=TaskStatus.COMPLETED.value, result={"ok": True})

    reloaded = TaskStore(path)
    task = reloaded.get("task-1")
    assert task is not None
    assert task["status"] == TaskStatus.COMPLETED.value
    assert task["result"] == {"ok": True}
    assert task["metadata"]["command"] == "agent.execute"


def test_task_store_lists_newest_first(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    for task_id, created_at in (("old", 1.0), ("new", 2.0)):
        store.create(
            {
                "id": task_id,
                "prompt": task_id,
                "model": None,
                "status": TaskStatus.QUEUED.value,
                "created_at": created_at,
                "started_at": None,
                "completed_at": None,
                "result": None,
                "error": None,
                "metadata": {},
            }
        )
    assert [task["id"] for task in store.list()] == ["new", "old"]
