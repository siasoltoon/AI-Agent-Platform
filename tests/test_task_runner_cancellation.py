import threading
import time

from backend.storage.task_store import TaskStore
from backend.task_runner import TaskRunner
from task_engine.contracts import TaskStatus


def _seed(store):
    store.create({
        "id": "task-1", "prompt": "Do work", "model": None,
        "status": TaskStatus.QUEUED.value, "created_at": time.time(),
        "started_at": None, "completed_at": None, "result": None,
        "error": None, "metadata": {"command": "agent.execute"},
    })


def test_cancelled_task_cannot_become_completed(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    _seed(store)
    gate = threading.Event()

    class Router:
        def route(self, task, *, task_id):
            gate.wait(1)
            return {"execution_mode": "agentic", "result": {"steps": 1}}

    runner = TaskRunner(store, Router(), poll_seconds=0.01)
    runner.start()
    try:
        deadline = time.time() + 1
        while time.time() < deadline and store.get("task-1")["status"] != "running":
            time.sleep(0.01)
        assert store.get("task-1")["status"] == "running"
        store.cancel("task-1", reason="user requested stop")
        gate.set()
        time.sleep(0.05)
    finally:
        gate.set()
        runner.stop()

    task = store.get("task-1")
    assert task["status"] == TaskStatus.CANCELLED.value
    assert task["error"] == "user requested stop"
