"""End-to-end integrity coverage for the real agent executor and task runner."""

import time
from pathlib import Path

from agent_core.execution_agent import AgentExecutor
from backend.storage.task_store import TaskStore
from backend.task_runner import TaskRunner
from task_engine.contracts import TaskStatus


class FakeOllama:
    timeout = 10

    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []

    def generate(self, prompt, timeout=None):
        self.prompts.append(prompt)
        return {"response": next(self.responses)}


class ExecutorRouter:
    def __init__(self, executor):
        self.executor = executor

    def route(self, task, *, task_id):
        return {
            "execution_mode": "agentic",
            "result": self.executor.execute(task.prompt),
        }


def seed(store, prompt):
    store.create(
        {
            "id": "e2e-integrity",
            "prompt": prompt,
            "model": None,
            "status": TaskStatus.QUEUED.value,
            "created_at": time.time(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
            "metadata": {
                "command": "agent.execute",
                "timeout_seconds": None,
                "max_retries": 0,
            },
        }
    )


def wait_for_terminal(store, task_id, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = store.get(task_id)
        if task and task["status"] in {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value}:
            return task
        time.sleep(0.02)
    raise AssertionError("Task did not reach a terminal state.")


def test_full_e2e_exact_content_integrity_survives_executor_and_runner(tmp_path: Path):
    target = "agent-full-e2e.txt"
    expected = "AI Agent Platform full E2E integrity passed."
    prompt = (
        f"Create {target} with exactly: {expected} "
        "Then directly read the created file and verify that its contents exactly match. "
        "Do not modify or delete any other files."
    )
    ollama = FakeOllama([
        '{"action":"write_file","tool":"write_file","args":{"path":"agent-full-e2e.txt","content":"AI Agent Platform full E2E integrity passed."}}',
        '{"action":"read_file","tool":"read_file","args":{"path":"agent-full-e2e.txt"}}',
        '{"action":"done","summary":"Created and directly read the exact file content."}',
    ])
    executor = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=32)
    store = TaskStore(tmp_path / "tasks.db")
    seed(store, prompt)

    runner = TaskRunner(store, ExecutorRouter(executor))
    runner.start()
    try:
        task = wait_for_terminal(store, "e2e-integrity")
    finally:
        runner.stop()

    assert task["status"] == TaskStatus.COMPLETED.value
    assert (tmp_path / target).read_text(encoding="utf-8") == expected

    evidence = task["metadata"]["execution_evidence"]
    assert evidence["verified"] is True
    assert evidence["scope_verified"] is True
    assert evidence["requested_paths"] == [target]
    assert evidence["unexpected_paths"] == []

    checks = evidence["checks"]
    assert any(
        check["type"] == "file_exists"
        and check["path"] == target
        and check["passed"] is True
        for check in checks
    )
    assert any(
        check["type"] == "file_content_matches_write"
        and check["path"] == target
        and check["passed"] is True
        and check["expected_content"] == expected
        for check in checks
    )
    assert any(
        check["type"] == "read_verified_exists"
        and check["path"] == target
        and check["passed"] is True
        for check in checks
    )
    assert any(
        check["type"] == "read_content_matches_write"
        and check["path"] == target
        and check["passed"] is True
        and check["actual_content"] == expected
        for check in checks
    )

    records = task["result"]["result"]["tool_records"]
    assert [record["tool"] for record in records] == ["write_file", "read_file"]
    assert "MANDATORY EXACT-CONTENT VERIFICATION PROTOCOL" in ollama.prompts[0]
