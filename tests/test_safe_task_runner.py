import time

from backend.safe_task_runner import SafeTaskRunner
from backend.storage.task_store import TaskStore
from task_engine.contracts import TaskStatus


class FakeRouter:
    def __init__(self, error):
        self.error = error

    def route(self, task, *, task_id):
        raise self.error


def seed(store):
    store.create(
        {
            "id": "ambiguous-task",
            "prompt": "Run an agent task",
            "model": None,
            "status": TaskStatus.QUEUED.value,
            "created_at": time.time(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
            "metadata": {"command": "agent.execute", "timeout_seconds": 300, "max_retries": 5},
        }
    )


def wait_for_terminal(store, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = store.get("ambiguous-task")
        if task and task["status"] in {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value}:
            return task
        time.sleep(0.02)
    raise AssertionError("Task did not reach a terminal state.")


def test_ambiguous_worker_timeout_is_not_automatically_retried(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    seed(store)
    runner = SafeTaskRunner(
        store,
        FakeRouter(RuntimeError("Worker request timed out after 300 seconds.")),
    )
    runner.start()
    try:
        task = wait_for_terminal(store)
    finally:
        runner.stop()

    assert task["status"] == TaskStatus.FAILED.value
    assert task["metadata"]["execution_ambiguous"] is True
    assert task["metadata"]["automatic_retry_suppressed"] is True
    assert task["metadata"].get("retry_count", 0) == 0


def test_ambiguous_worker_5xx_is_not_automatically_retried(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    seed(store)
    runner = SafeTaskRunner(
        store,
        FakeRouter(RuntimeError("Worker HTTP 500: ReadTimeout: upstream timeout")),
    )
    runner.start()
    try:
        task = wait_for_terminal(store)
    finally:
        runner.stop()

    assert task["status"] == TaskStatus.FAILED.value
    assert task["metadata"]["execution_ambiguous"] is True
    assert task["metadata"]["automatic_retry_suppressed"] is True


def test_definitive_failures_keep_existing_retry_policy(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    seed(store)
    runner = SafeTaskRunner(store, FakeRouter(RuntimeError("validation failed")))

    record = store.get("ambiguous-task")
    record["status"] = TaskStatus.RUNNING.value
    runner._fail_or_retry("ambiguous-task", record, "validation failed")

    task = store.get("ambiguous-task")
    assert task["status"] == TaskStatus.QUEUED.value
    assert task["metadata"]["retry_count"] == 1
