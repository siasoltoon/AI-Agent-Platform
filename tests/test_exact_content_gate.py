"""Regression coverage for deterministic exact-content completion gating."""

from pathlib import Path

from backend.storage.task_store import TaskStore
from backend.task_runner import TaskRunner
from task_engine.contracts import TaskStatus
from task_engine.exact_content_gate import extract_exact_content_requirements, verify_exact_content


class Router:
    def __init__(self, result):
        self.result = result

    def route(self, task, *, task_id):
        return self.result


def _evidence(path: str, write_content: str, read_content: str):
    return {
        "verified": True,
        "checks": [
            {"type": "file_exists", "path": path, "passed": True},
            {"type": "file_content_matches_write", "path": path, "expected_content": write_content, "passed": True},
            {"type": "read_verified_exists", "path": path, "passed": True},
            {"type": "read_content_matches_write", "path": path, "expected_content": write_content, "actual_content": read_content, "passed": read_content == write_content},
        ],
    }


def test_extracts_multiline_exact_content_from_task():
    prompt = (
        "Create agent-test.txt. The file must contain exactly these three lines:\n"
        "AI Agent Platform\n"
        "Production Test\n"
        "Hello World\n"
        "After creating it, directly read the file."
    )
    assert extract_exact_content_requirements(prompt) == {
        "agent-test.txt": "AI Agent Platform\nProduction Test\nHello World"
    }


def test_exact_gate_rejects_content_that_only_matches_the_agent_write():
    prompt = "Create agent-test.txt. The file must contain exactly: expected-content. Then read it."
    evidence = _evidence("agent-test.txt", "wrong-content.", "wrong-content.")
    result = verify_exact_content(prompt, evidence)
    assert result["exact_content_required"] is True
    assert result["exact_content_verified"] is False
    assert "requested_content_differs_from_write:agent-test.txt" in result["exact_content_blockers"]


def test_exact_gate_requires_direct_read_to_match_requested_content():
    prompt = "Create agent-test.txt with exactly: expected-content. Then read it."
    evidence = _evidence("agent-test.txt", "expected-content.", "tampered.")
    result = verify_exact_content(prompt, evidence)
    assert result["exact_content_verified"] is False
    assert "read_content_not_verified:agent-test.txt" in result["exact_content_blockers"]


def test_exact_gate_accepts_requested_write_and_direct_read_match():
    prompt = "Create agent-test.txt with exactly: expected-content. Then read it."
    evidence = _evidence("agent-test.txt", "expected-content.", "expected-content.")
    result = verify_exact_content(prompt, evidence)
    assert result["exact_content_verified"] is True
    assert result["exact_content_blockers"] == []


def test_exact_gate_fails_closed_when_exact_requirement_is_ambiguous():
    prompt = "Create agent-test.txt with exactly the requested content. Then read it."
    result = verify_exact_content(prompt, {"checks": []})
    assert result["exact_content_required"] is True
    assert result["exact_content_verified"] is False
    assert "exact_content_requirement_unparseable" in result["exact_content_blockers"]


def test_runner_rejects_read_equals_write_when_requested_content_differs(tmp_path: Path):
    prompt = (
        "Create agent-test.txt with exactly:\n"
        "AI Agent Platform\n"
        "Production Test\n"
        "Hello World\n"
        "Then directly read agent-test.txt and verify the exact content."
    )
    actual = "AI Agent Platform Production Test\nHello World"
    (tmp_path / "agent-test.txt").write_text(actual, encoding="utf-8")

    result = {
        "execution_mode": "agentic",
        "result": {
            "status": "completed",
            "execution_evidence": _evidence("agent-test.txt", actual, actual),
            "tool_records": [
                {"ok": True, "tool": "write_file", "result": {"path": "agent-test.txt", "content": actual}},
                {"ok": True, "tool": "read_file", "result": {"path": "agent-test.txt", "content": actual}},
            ],
        },
    }

    store = TaskStore(tmp_path / "tasks.db")
    store.create({
        "id": "exact-gate",
        "prompt": prompt,
        "model": None,
        "status": TaskStatus.QUEUED.value,
        "created_at": 1.0,
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "metadata": {"max_retries": 0},
    })

    runner = TaskRunner(store, Router(result))
    runner.start()
    try:
        import time
        deadline = time.time() + 3
        while time.time() < deadline:
            task = store.get("exact-gate")
            if task and task["status"] in {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value}:
                break
            time.sleep(0.02)
    finally:
        runner.stop()

    task = store.get("exact-gate")
    assert task["status"] == TaskStatus.FAILED.value
    assert "exact content" in task["error"].lower()
