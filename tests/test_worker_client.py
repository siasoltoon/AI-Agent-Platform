import pytest

from backend.services.worker_client import WorkerClient


class FakeResponse:
    def __init__(self, status_code=422, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.reason = "Unprocessable Content"

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_worker_client_preserves_structured_worker_error(monkeypatch):
    response = FakeResponse(
        422,
        {"detail": {"message": "Agent could not complete the task.", "error": "Model did not return a valid JSON action.", "task_id": "task-1"}},
    )

    monkeypatch.setattr("backend.services.worker_client.requests.post", lambda *args, **kwargs: response)

    with pytest.raises(RuntimeError, match="Worker HTTP 422: Model did not return a valid JSON action"):
        WorkerClient("127.0.0.1", 8001).execute_task({"task_id": "task-1", "prompt": "test"})


def test_worker_client_reports_non_json_worker_error(monkeypatch):
    response = FakeResponse(500, ValueError("not json"), text="worker crashed")

    monkeypatch.setattr("backend.services.worker_client.requests.post", lambda *args, **kwargs: response)

    with pytest.raises(RuntimeError, match="Worker HTTP 500: worker crashed"):
        WorkerClient("127.0.0.1", 8001).execute_task({"prompt": "test"})
