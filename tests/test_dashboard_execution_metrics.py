from pathlib import Path

from backend.api import dashboard, tasks
from backend.storage.execution_ledger import ExecutionLedger
from backend.storage.side_effect_ledger import SideEffectLedger
from backend.storage.task_store import TaskStore


def test_dashboard_summary_exposes_authoritative_execution_metrics(monkeypatch, tmp_path: Path):
    db = tmp_path / "tasks.db"
    store = TaskStore(db)
    monkeypatch.setattr(tasks, "TASK_STORE", store)

    ledger = ExecutionLedger(db)
    ledger.begin("task-1", "worker-1", execution_id="exec-1")
    effects = SideEffectLedger(db)
    effects.begin(
        idempotency_key="effect-1",
        task_id="task-1",
        execution_id="exec-1",
        fencing_token=1,
        tool_name="write_file",
        request_hash="hash-1",
    )

    payload = dashboard.dashboard_summary()
    execution = payload["execution"]
    assert execution["status"] == "ok"
    assert execution["attempts"]["total"] == 1
    assert execution["attempts"]["running"] == 1
    assert execution["side_effects"]["total"] == 1
    assert execution["side_effects"]["running"] == 1


def test_dashboard_execution_failure_is_not_reported_healthy(monkeypatch, tmp_path: Path):
    store = TaskStore(tmp_path / "tasks.db")
    monkeypatch.setattr(tasks, "TASK_STORE", store)

    class BrokenLedger:
        def __init__(self, path):
            raise RuntimeError("execution ledger unavailable")

    monkeypatch.setattr(dashboard, "ExecutionLedger", BrokenLedger)
    payload = dashboard.dashboard_summary()
    assert payload["execution"]["status"] == "offline"
    assert "unavailable" in payload["execution"]["error"]
