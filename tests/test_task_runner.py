import time

from backend.storage.task_store import TaskStore
from backend.task_runner import TaskRunner
from task_engine.contracts import TaskStatus


class FakeRouter:
    def __init__(self, result=None, error=None):
        self.result = result or {"execution_mode": "agentic", "result": {"steps": 2}}
        self.error = error

    def route(self, task, *, task_id):
        if self.error:
            raise self.error
        return self.result


def seed(store, task_id="task-1"):
    store.create(
        {
            "id": task_id,
            "prompt": "Create hello.txt",
            "model": None,
            "status": TaskStatus.QUEUED.value,
            "created_at": time.time(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
            "metadata": {"command": "agent.execute", "timeout_seconds": None},
        }
    )


def wait_for_terminal(store, task_id, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = store.get(task_id)
        if task and task["status"] in {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value}:
            return task
        time.sleep(0.02)
    raise AssertionError("Task did not reach a terminal state.")


def test_runner_executes_queued_task_and_persists_result(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    seed(store)
    runner = TaskRunner(store, FakeRouter())
    runner.start()
    try:
        task = wait_for_terminal(store, "task-1")
    finally:
        runner.stop()

    assert task["status"] == TaskStatus.COMPLETED.value
    assert task["result"]["result"]["steps"] == 2
    assert task["metadata"]["execution_mode"] == "agentic"


def test_runner_persists_execution_failure(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    seed(store)
    runner = TaskRunner(store, FakeRouter(error=RuntimeError("worker offline")))
    runner.start()
    try:
        task = wait_for_terminal(store, "task-1")
    finally:
        runner.stop()

    assert task["status"] == TaskStatus.FAILED.value
    assert task["error"] == "worker offline"


def test_runner_recovers_interrupted_running_tasks(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    seed(store)
    store.update("task-1", status=TaskStatus.RUNNING.value, started_at=time.time())

    runner = TaskRunner(store, FakeRouter())
    runner.start()
    try:
        task = wait_for_terminal(store, "task-1")
    finally:
        runner.stop()

    assert task["status"] == TaskStatus.COMPLETED.value
