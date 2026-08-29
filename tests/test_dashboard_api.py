from pathlib import Path

from backend.api import dashboard, tasks
from backend.storage.task_store import TaskStore
from task_engine.contracts import TaskStatus


def test_dashboard_summary_uses_real_task_state(monkeypatch, tmp_path: Path):
    store = TaskStore(tmp_path / "tasks.db")
    store.create({
        "id": "task-1",
        "prompt": "hello",
        "model": "test-model",
        "status": TaskStatus.QUEUED.value,
        "created_at": 1.0,
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "metadata": {},
    })
    monkeypatch.setattr(tasks, "TASK_STORE", store)
    monkeypatch.setattr(dashboard.agents.runtime, "health_check", lambda: {"status": "ready"})
    monkeypatch.setattr(dashboard.workers, "list_workers", lambda: {"workers": []})

    payload = dashboard.dashboard_summary()

    assert payload["tasks"]["counts"]["total"] == 1
    assert payload["tasks"]["counts"]["queued"] == 1
    assert payload["tasks"]["counts"]["completed"] == 0
    assert payload["tasks"]["event_count"] == 1
    assert payload["tasks"]["recent_events"][0]["event_type"] == "created"
    assert payload["agent"]["status"] == "ready"
    assert payload["workers"]["workers"] == []


def test_dashboard_diagnostics_reports_task_store(monkeypatch, tmp_path: Path):
    store = TaskStore(tmp_path / "tasks.db")
    monkeypatch.setattr(tasks, "TASK_STORE", store)
    monkeypatch.setattr(dashboard.agents.runtime, "health_check", lambda: {"status": "ready"})
    monkeypatch.setattr(dashboard.workers, "list_workers", lambda: {"workers": []})

    payload = dashboard.dashboard_diagnostics()

    assert [check["status"] for check in payload["checks"]] == ["pass", "pass", "pass"]
