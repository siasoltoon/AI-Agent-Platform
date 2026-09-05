import time

from backend.storage.task_store import TaskStore
from backend.task_runner import TaskRunner
from task_engine.contracts import TaskStatus


class FakeRouter:
    def __init__(self, result=None, error=None):
        self.result = result or {
            "execution_mode": "agentic",
            "result": {
                "status": "completed",
                "execution_evidence": {"verified": True, "checks": [{"type": "file_exists", "path": "hello.txt", "passed": True}]},
                "tool_records": [{"ok": True, "tool": "write_file"}],
                "steps": 2,
            },
        }
        self.error = error

    def route(self, task, *, task_id):
        if self.error:
            raise self.error
        return self.result


def seed(store, task_id="task-1", prompt="Create hello.txt"):
    store.create(
        {
            "id": task_id,
            "prompt": prompt,
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
    assert task["metadata"]["execution_evidence"]["verified"] is True
    assert task["error"] is None


def test_runner_rejects_completion_without_verified_evidence(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    seed(store)
    result = {
        "execution_mode": "agentic",
        "result": {"status": "completed", "execution_evidence": {"verified": False}, "tool_records": [{"ok": True}]},
    }
    runner = TaskRunner(store, FakeRouter(result=result))
    runner.start()
    try:
        task = wait_for_terminal(store, "task-1")
    finally:
        runner.stop()

    assert task["status"] == TaskStatus.FAILED.value
    assert "verified execution evidence" in task["error"]


def test_runner_rejects_verified_but_irrelevant_file_evidence(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    seed(store, prompt="Create requested.txt")
    result = {
        "execution_mode": "agentic",
        "result": {
            "status": "completed",
            "execution_evidence": {"verified": True, "checks": [{"type": "file_exists", "path": "other.txt", "passed": True}]},
            "tool_records": [{"ok": True, "tool": "write_file", "result": {"path": "other.txt"}}],
        },
    }
    runner = TaskRunner(store, FakeRouter(result=result))
    runner.start()
    try:
        task = wait_for_terminal(store, "task-1")
    finally:
        runner.stop()

    assert task["status"] == TaskStatus.FAILED.value
    assert "does not prove the requested file state" in task["error"]


def test_runner_requires_exact_content_evidence_for_exact_file_task(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    seed(store, prompt="Create exact.txt with exactly: expected")
    result = {
        "execution_mode": "agentic",
        "result": {
            "status": "completed",
            "execution_evidence": {"verified": True, "checks": [{"type": "file_exists", "path": "exact.txt", "passed": True}]},
            "tool_records": [{"ok": True, "tool": "write_file", "result": {"path": "exact.txt"}}],
        },
    }
    runner = TaskRunner(store, FakeRouter(result=result))
    runner.start()
    try:
        task = wait_for_terminal(store, "task-1")
    finally:
        runner.stop()

    assert task["status"] == TaskStatus.FAILED.value


def test_runner_rejects_unexpected_mutation_for_restricted_task(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    seed(store, prompt="Create requested.txt. Do not modify or delete any other files.")
    store.update("task-1", metadata={"command": "agent.execute", "timeout_seconds": None, "max_retries": 0})
    result = {
        "execution_mode": "agentic",
        "result": {
            "status": "completed",
            "execution_evidence": {
                "verified": True,
                "checks": [
                    {"type": "file_exists", "path": "requested.txt", "passed": True},
                    {"type": "file_content_matches_write", "path": "requested.txt", "passed": True},
                ],
            },
            "tool_records": [
                {"ok": True, "tool": "write_file", "result": {"path": "requested.txt", "content": "ok"}},
                {"ok": True, "tool": "make_directory", "result": {"path": "test_directory"}},
            ],
        },
    }
    runner = TaskRunner(store, FakeRouter(result=result))
    runner.start()
    try:
        task = wait_for_terminal(store, "task-1")
    finally:
        runner.stop()

    assert task["status"] == TaskStatus.FAILED.value
    assert "unauthorized workspace side effects" in task["error"]


def test_runner_accepts_only_requested_mutation_for_restricted_task(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    seed(store, prompt="Create requested.txt. Do not modify or delete any other files.")
    result = {
        "execution_mode": "agentic",
        "result": {
            "status": "completed",
            "execution_evidence": {
                "verified": True,
                "checks": [
                    {"type": "file_exists", "path": "requested.txt", "passed": True},
                    {"type": "file_content_matches_write", "path": "requested.txt", "passed": True},
                ],
            },
            "tool_records": [
                {"ok": True, "tool": "write_file", "result": {"path": "requested.txt", "content": "ok"}},
            ],
        },
    }
    runner = TaskRunner(store, FakeRouter(result=result))
    runner.start()
    try:
        task = wait_for_terminal(store, "task-1")
    finally:
        runner.stop()

    assert task["status"] == TaskStatus.COMPLETED.value
    evidence = task["metadata"]["execution_evidence"]
    assert evidence["scope_verified"] is True
    assert evidence["requested_paths"] == ["requested.txt"]
    assert evidence["unexpected_paths"] == []


def test_runner_rejects_unscoped_terminal_mutation_for_restricted_task(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    seed(store, prompt="Create requested.txt. Do not modify anything else.")
    result = {
        "execution_mode": "agentic",
        "result": {
            "status": "completed",
            "execution_evidence": {
                "verified": True,
                "checks": [
                    {"type": "file_exists", "path": "requested.txt", "passed": True},
                    {"type": "file_content_matches_write", "path": "requested.txt", "passed": True},
                ],
            },
            "tool_records": [
                {"ok": True, "tool": "write_file", "result": {"path": "requested.txt", "content": "ok"}},
                {"ok": True, "tool": "terminal", "result": {"command": "echo extra > other.txt", "code": 0}},
            ],
        },
    }
    runner = TaskRunner(store, FakeRouter(result=result))
    runner.start()
    try:
        task = wait_for_terminal(store, "task-1")
    finally:
        runner.stop()

    assert task["status"] == TaskStatus.FAILED.value


def test_runner_rejects_terminal_mkdir_for_restricted_task(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    seed(store, prompt="Create requested.txt. Do not modify or delete any other files.")
    result = {
        "execution_mode": "agentic",
        "result": {
            "status": "completed",
            "execution_evidence": {
                "verified": True,
                "checks": [
                    {"type": "file_exists", "path": "requested.txt", "passed": True},
                    {"type": "file_content_matches_write", "path": "requested.txt", "passed": True},
                ],
            },
            "tool_records": [
                {"ok": True, "tool": "write_file", "result": {"path": "requested.txt", "content": "ok"}},
                {"ok": True, "tool": "terminal", "result": {"command": "mkdir test_directory", "code": 0}},
            ],
        },
    }
    runner = TaskRunner(store, FakeRouter(result=result))
    runner.start()
    try:
        task = wait_for_terminal(store, "task-1")
    finally:
        runner.stop()

    assert task["status"] == TaskStatus.FAILED.value


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
