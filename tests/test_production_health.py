from fastapi.testclient import TestClient

from backend.main import app


def test_liveness_probe_is_ok():
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_probe_reports_task_store():
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["task_store"] == "ok"
