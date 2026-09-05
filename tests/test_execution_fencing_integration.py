import time

from backend.recovery_sweep import RecoverySweep
from backend.safe_task_runner import SafeTaskRunner
from backend.storage.execution_ledger import ExecutionLedger
from backend.storage.task_store import TaskStore
from backend.storage.worker_lease_store import WorkerLeaseStore
from task_engine.contracts import TaskStatus


class SuccessfulRouter:
    def route(self, task, *, task_id):
        return {
            "execution_mode": "agentic",
            "result": {"steps": 1, "mode": "agentic"},
            "execution_evidence": {"verified": True, "checks": []},
        }


def seed(store, task_id="task-1"):
    store.create({
        "id": task_id,
        "prompt": "Run an agent task",
        "model": None,
        "status": TaskStatus.QUEUED.value,
        "created_at": time.time(),
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "metadata": {"command": "agent.execute", "max_retries": 5},
    })


def test_success_is_committed_to_task_and_ledger_atomically(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    seed(store)
    claimed = store.claim_next_queued()
    runner = SafeTaskRunner(store, SuccessfulRouter(), worker_id="worker-a")

    runner._execute(claimed)

    task = store.get("task-1")
    attempt = runner.execution_ledger.current("task-1")
    assert task["status"] == TaskStatus.COMPLETED.value
    assert attempt["state"] == "committed"
    assert task["metadata"]["fencing_token"] == attempt["fencing_token"]


def test_stale_attempt_is_marked_ambiguous_after_recovery(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    leases = WorkerLeaseStore(tmp_path / "tasks.db")
    ledger = ExecutionLedger(tmp_path / "tasks.db")
    seed(store)
    store.claim_next_queued()
    attempt = ledger.begin("task-1", "dead-worker")
    leases.acquire("task-1", "dead-worker", attempt["execution_id"], ttl_seconds=5, now=100.0)

    result = RecoverySweep(store, leases, execution_ledger=ledger).sweep(now=200.0)

    assert result["stale_leases"] == 1
    assert store.get("task-1")["status"] == TaskStatus.FAILED.value
    assert ledger.get(attempt["execution_id"])["state"] == "ambiguous"
