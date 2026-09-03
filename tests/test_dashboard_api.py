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


def test_dashboard_diagnostics_reports_task_store(monkeypatch, tmp_path: Path):
    store = TaskStore(tmp_path / "tasks.db")
    monkeypatch.setattr(tasks, "TASK_STORE", store)
    monkeypatch.setattr(dashboard.agents.runtime, "health_check", lambda: {"status": "ready"})
    monkeypatch.setattr(dashboard.workers, "list_workers", lambda: {"workers": []})

    payload = dashboard.dashboard_diagnostics()

    assert [check["status"] for check in payload["checks"]] == ["pass", "pass", "pass"]


def test_completed_resume_dashboard_script_is_wired_into_served_surface():
    route_paths = {getattr(route, "path", None) for route in app.routes}
    assert "/dashboard/completed-resume.js" in route_paths

    index_html = Path("dashboard/index.html").read_text(encoding="utf-8")
    resume_js = Path("dashboard/completed-resume.js").read_text(encoding="utf-8")
    app_js = Path("dashboard/app.js").read_text(encoding="utf-8")

    assert '<script src="/dashboard/completed-resume.js" defer></script>' in index_html
    assert '<script src="/dashboard/app.js" defer></script>' in index_html
    assert index_html.index('completed-resume.js') < index_html.index('app.js')
    assert "/tasks/${encodeURIComponent(taskId)}/resume" in resume_js
    assert 'data-completed-resume=' in resume_js
    assert 'observer.observe(document.body' in resume_js
    assert 'data-resume-task=' in app_js
    assert '/tasks/${encodeURIComponent(id)}/resume' in app_js
