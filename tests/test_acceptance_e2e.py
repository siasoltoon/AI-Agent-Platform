import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.api import tasks
from backend.storage.task_store import TaskStore
from task_engine.contracts import TaskStatus


class AcceptanceRouter:
    def __init__(self, *, block=False):
        self.block = block
        self.started = threading.Event()
        self.release = threading.Event()

    def command_for(self, task):
        command = task.metadata.get("command", "agent.execute")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("Task command cannot be empty.")
        return command.strip().lower()

    def route(self, task, *, task_id):
        self.started.set()
        if self.block:
            self.release.wait(timeout=2)
        return {
            "execution_mode": "agentic",
            "result": {
                "status": "completed",
                "execution_evidence": {
                    "verified": True,
                    "checks": [
                        {"type": "file_exists", "path": "acceptance.txt", "passed": True},
                        {"type": "read_verified_exists", "path": "acceptance.txt", "passed": True},
                        {"type": "file_content_matches_write", "path": "acceptance.txt", "passed": True, "expected_content": "accepted"},
                        {"type": "read_content_matches_write", "path": "acceptance.txt", "passed": True, "actual_content": "accepted"},
                    ],
                },
                "tool_records": [
                    {"ok": True, "tool": "write_file", "result": {"path": "acceptance.txt", "content": "accepted"}},
                    {"ok": True, "tool": "read_file", "result": {"path": "acceptance.txt", "content": "accepted"}},
                ],
                "steps": 2,
            },
        }


@pytest.fixture
def isolated_app(monkeypatch, tmp_path):
    store = TaskStore(tmp_path / "acceptance.db")
    router = AcceptanceRouter()
    monkeypatch.setattr(tasks, "TASK_STORE", store)
    monkeypatch.setattr(tasks, "task_router", router)
    yield store, router


def wait_for_status(store, task_id, expected, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = store.get(task_id)
        if task and task["status"] == expected:
            return task
        time.sleep(0.02)
    raise AssertionError(f"Task did not reach {expected!r}.")


def test_full_acceptance_chain_api_queue_runner_evidence_persistence(isolated_app):
    store, _ = isolated_app

    with TestClient(main.app) as client:
        response = client.post(
            "/tasks/",
            json={"task_id": "acceptance-1", "prompt": "Create acceptance.txt with exactly: accepted"},
        )
        assert response.status_code == 202
        assert response.json()["status"] == TaskStatus.QUEUED.value

        completed = wait_for_status(store, "acceptance-1", TaskStatus.COMPLETED.value)
        fetched = client.get("/tasks/acceptance-1")

    assert fetched.status_code == 200
    payload = fetched.json()
    assert payload["status"] == TaskStatus.COMPLETED.value
    assert payload["result"]["result"]["steps"] == 2
    assert payload["metadata"]["execution_mode"] == "agentic"
    assert payload["metadata"]["execution_evidence"]["verified"] is True
    assert payload["metadata"]["execution_evidence"]["scope_restricted"] is False
    assert payload["metadata"]["execution_evidence"]["scope_verified"] is False
    assert completed["error"] is None


def test_acceptance_rejects_unverified_completion(monkeypatch, isolated_app):
    store, _ = isolated_app

    class UnverifiedRouter(AcceptanceRouter):
        def route(self, task, *, task_id):
            return {
                "execution_mode": "agentic",
                "result": {
                    "status": "completed",
                    "execution_evidence": {"verified": False},
                    "tool_records": [],
                },
            }

    monkeypatch.setattr(tasks, "task_router", UnverifiedRouter())
    with TestClient(main.app) as client:
        response = client.post("/tasks/", json={"task_id": "reject-1", "prompt": "Create acceptance.txt"})
        assert response.status_code == 202
        task = wait_for_status(store, "reject-1", TaskStatus.FAILED.value)

    assert task["status"] == TaskStatus.FAILED.value
    assert "verified execution evidence" in task["error"]


def test_cancellation_prevents_post_cancel_success(monkeypatch, isolated_app):
    store, _ = isolated_app
    router = AcceptanceRouter(block=True)
    monkeypatch.setattr(tasks, "task_router", router)

    with TestClient(main.app) as client:
        response = client.post("/tasks/", json={"task_id": "cancel-1", "prompt": "Create acceptance.txt"})
        assert response.status_code == 202
        assert router.started.wait(timeout=1)

        cancelled = client.post("/tasks/cancel-1/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == TaskStatus.CANCELLED.value

        router.release.set()
        task = wait_for_status(store, "cancel-1", TaskStatus.CANCELLED.value)

    assert task["status"] == TaskStatus.CANCELLED.value
    assert task["result"] is None


def test_acceptance_health_gate_is_ready(isolated_app):
    with TestClient(main.app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

    assert live.status_code == 200
    assert ready.status_code == 200
    assert live.json()["status"] == "ok"
    assert ready.json()["status"] == "ready"
    assert ready.json()["checks"] == {"task_store": "ok", "task_runner": "ok"}
