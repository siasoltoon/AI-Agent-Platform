import pytest

from backend.services.worker_client import WorkerClient, WorkerExecutionError


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

    with pytest.raises(WorkerExecutionError, match="Worker HTTP 422: Model did not return a valid JSON action") as exc_info:
        WorkerClient("127.0.0.1", 8001).execute_task({"task_id": "task-1", "prompt": "test"})

    error = exc_info.value
    assert error.retryable is False
    assert error.ambiguous is False
    assert error.status_code == 422
    assert error.task_id == "task-1"


def test_worker_client_reports_non_json_worker_error(monkeypatch):
    response = FakeResponse(500, ValueError("not json"), text="worker crashed")

    monkeypatch.setattr("backend.services.worker_client.requests.post", lambda *args, **kwargs: response)

    with pytest.raises(WorkerExecutionError, match="Worker HTTP 500: worker crashed") as exc_info:
        WorkerClient("127.0.0.1", 8001).execute_task({"task_id": "task-1", "prompt": "test"})

    error = exc_info.value
    assert error.retryable is True
    assert error.ambiguous is True
    assert error.status_code == 500
    assert error.task_id == "task-1"


def test_worker_client_marks_timeout_as_ambiguous(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise TimeoutError("network timeout")

    monkeypatch.setattr("backend.services.worker_client.requests.post", raise_timeout)

    # requests.Timeout is intentionally raised here so the client can preserve
    # the distinction between an ambiguous execution and a definitive failure.
    import requests

    def raise_requests_timeout(*args, **kwargs):
        raise requests.Timeout("network timeout")

    monkeypatch.setattr("backend.services.worker_client.requests.post", raise_requests_timeout)

    with pytest.raises(WorkerExecutionError) as exc_info:
        WorkerClient("127.0.0.1", 8001).execute_task({"task_id": "task-2", "prompt": "write once", "timeout": 5})

    error = exc_info.value
    assert error.retryable is True
    assert error.ambiguous is True
    assert error.status_code is None
    assert error.task_id == "task-2"


def test_worker_client_marks_connection_failure_as_ambiguous(monkeypatch):
    import requests

    def raise_connection_error(*args, **kwargs):
        raise requests.ConnectionError("connection reset")

    monkeypatch.setattr("backend.services.worker_client.requests.post", raise_connection_error)

    with pytest.raises(WorkerExecutionError) as exc_info:
        WorkerClient("127.0.0.1", 8001).execute_task({"task_id": "task-3", "prompt": "write once"})

    error = exc_info.value
    assert error.retryable is True
    assert error.ambiguous is True
    assert error.task_id == "task-3"
