from fastapi.testclient import TestClient

from backend.main import app


def test_liveness_probe_is_ok():
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_probe_reports_task_store():
    # Readiness depends on the production lifespan starting the background runner.
    # TestClient without a context manager does not enter the app lifespan.
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["task_store"] == "ok"
    assert payload["checks"]["task_runner"] == "ok"
