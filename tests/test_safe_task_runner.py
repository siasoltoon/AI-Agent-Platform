import time

from backend.safe_task_runner import SafeTaskRunner
from backend.storage.task_store import TaskStore
from backend.storage.worker_lease_store import WorkerLeaseStore
from task_engine.contracts import TaskStatus


class FakeRouter:
    def __init__(self, error):
        self.error = error

    def route(self, task, *, task_id):
        raise self.error


class LeaseStealingRouter:
    def __init__(self, lease_store):
        self.lease_store = lease_store

    def route(self, task, *, task_id):
        lease = self.lease_store.get(task_id)
        assert lease is not None
        self.lease_store.release(task_id, lease["worker_id"], lease["execution_id"])
        return {
            "execution_mode": "agentic",
            "execution_evidence": {"verified": True, "checks": []},
        }


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
    runner._fail_or_retry("ambiguous-task", record, "validation failed")

    task = store.get("ambiguous-task")
    assert task["status"] == TaskStatus.QUEUED.value


def test_execution_identity_is_persisted_when_task_is_claimed(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    lease_store = WorkerLeaseStore(tmp_path / "tasks.db")
    seed(store)
    claimed = store.claim_next_queued()
    runner = SafeTaskRunner(
        store,
        FakeRouter(RuntimeError("Worker request timed out")),
        lease_store=lease_store,
        worker_id="worker-a",
    )

    runner._execute(claimed)

    task = store.get("ambiguous-task")
    assert task["metadata"]["worker_id"] == "worker-a"
    assert task["metadata"]["execution_id"]
    assert task["metadata"]["recovery_required"] is True
    assert lease_store.get("ambiguous-task") is None


def test_lost_lease_rejects_success_before_completed_state(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    lease_store = WorkerLeaseStore(tmp_path / "tasks.db")
    seed(store)
    claimed = store.claim_next_queued()
    runner = SafeTaskRunner(
        store,
        LeaseStealingRouter(lease_store),
        lease_store=lease_store,
        worker_id="worker-a",
    )

    runner._execute(claimed)

    task = store.get("ambiguous-task")
    assert task["status"] == TaskStatus.FAILED.value
    assert task["metadata"]["execution_ambiguous"] is True
    assert task["metadata"]["automatic_retry_suppressed"] is True
    assert "Execution lease lost" in task["error"]
