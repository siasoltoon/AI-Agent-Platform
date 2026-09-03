    monkeypatch.setattr(tasks, "TASK_STORE", store)
    monkeypatch.setattr(dashboard.agents.runtime, "health_check", lambda: {"status": "ready"})
    monkeypatch.setattr(dashboard.workers, "list_workers", lambda: {"workers": []})

    payload = dashboard.dashboard_diagnostics()

    assert [check["status"] for check in payload["checks"]] == ["pass", "pass", "pass"]


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