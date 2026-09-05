from pathlib import Path

from backend.api import dashboard, tasks
from backend.main import app
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


def test_dashboard_diagnostics_reports_task_store_and_execution_ledger(monkeypatch, tmp_path: Path):
    store = TaskStore(tmp_path / "tasks.db")
    monkeypatch.setattr(tasks, "TASK_STORE", store)
    monkeypatch.setattr(dashboard.agents.runtime, "health_check", lambda: {"status": "ready"})
    monkeypatch.setattr(dashboard.workers, "list_workers", lambda: {"workers": []})

    payload = dashboard.dashboard_diagnostics()

    assert [check["status"] for check in payload["checks"]] == ["pass", "pass", "pass", "pass"]
    assert [check["name"] for check in payload["checks"]] == [
        "Task Store", "Agent Worker", "Worker Registry", "Execution Fence Ledger"
    ]


def test_dashboard_diagnostics_fails_when_execution_ledger_unavailable(monkeypatch, tmp_path: Path):
    store = TaskStore(tmp_path / "tasks.db")
    monkeypatch.setattr(tasks, "TASK_STORE", store)
    monkeypatch.setattr(dashboard.agents.runtime, "health_check", lambda: {"status": "ready"})
    monkeypatch.setattr(dashboard.workers, "list_workers", lambda: {"workers": []})

    class BrokenLedger:
        def __init__(self, path):
            raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(dashboard, "ExecutionLedger", BrokenLedger)
    payload = dashboard.dashboard_diagnostics()

    assert payload["checks"][-1]["name"] == "Execution Fence Ledger"
    assert payload["checks"][-1]["status"] == "fail"


def test_completed_resume_is_single_source_of_truth_in_main_dashboard():
    route_paths = {getattr(route, "path", None) for route in app.routes}
    assert "/dashboard/completed-resume.js" not in route_paths

    index_html = Path("dashboard/index.html").read_text(encoding="utf-8")
    app_js = Path("dashboard/app.js").read_text(encoding="utf-8")
    helper = Path("dashboard/completed-resume.js")

    assert not helper.exists()
    assert '<script src="/dashboard/app.js?v=20260903-resume-v3" defer></script>' in index_html
    assert "completed-resume.js" not in index_html
    assert 'const normalizeStatus = (status) =>' in app_js
    assert 'String(status || "").trim().toLowerCase()' in app_js
    assert 'const status=normalizeStatus(t.status); const resume=status==="completed"' in app_js
    assert 'data-resume-task=' in app_js
    assert '/tasks/${encodeURIComponent(id)}/resume' in app_js
    assert 'document.getElementById("app")' in app_js
    assert 'root.innerHTML = shell()' in app_js
    assert 'document.body.innerHTML=shell()' not in app_js
