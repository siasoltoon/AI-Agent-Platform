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


def test_committed_execution_is_reconciled_after_crash_window(tmp_path):
    db = tmp_path / "tasks.db"
    store = TaskStore(db)
    leases = WorkerLeaseStore(db)
    ledger = ExecutionLedger(db)
    seed(store)
    store.claim_next_queued()
    attempt = ledger.begin("task-1", "worker-a", execution_id="exec-committed")
    result = {"execution_mode": "agentic", "result": {"steps": 2}, "execution_evidence": {"verified": True}}
    assert ledger.commit_if_current(
        "task-1",
        "exec-committed",
        attempt["fencing_token"],
        result=result,
    ) is True

    recovery = RecoverySweep(store, leases, execution_ledger=ledger)
    outcome = recovery.sweep(now=time.time())

    assert store.get("task-1")["status"] == TaskStatus.COMPLETED.value
    assert ledger.get("exec-committed")["state"] == "committed"
    assert any(item["action"] == "committed_execution_reconciled" for item in outcome["actions"])


def test_committed_old_execution_cannot_be_reconciled_after_newer_attempt(tmp_path):
    db = tmp_path / "tasks.db"
    store = TaskStore(db)
    leases = WorkerLeaseStore(db)
    ledger = ExecutionLedger(db)
    seed(store)
    store.claim_next_queued()
    first = ledger.begin("task-1", "worker-a", execution_id="exec-old")
    old_result = {"execution_mode": "agentic", "result": {"winner": "old"}}
    assert ledger.commit_if_current(
        "task-1",
        "exec-old",
        first["fencing_token"],
        result=old_result,
    ) is True
    second = ledger.begin("task-1", "worker-b", execution_id="exec-new")

    assert second["fencing_token"] > first["fencing_token"]
    recovery = RecoverySweep(store, leases, execution_ledger=ledger)
    outcome = recovery.sweep(now=time.time())

    assert store.get("task-1")["status"] == TaskStatus.FAILED.value
    assert ledger.get("exec-old")["state"] == "committed"
    assert ledger.get("exec-new")["state"] == "ambiguous"
    assert all(item["action"] != "committed_execution_reconciled" for item in outcome["actions"])
