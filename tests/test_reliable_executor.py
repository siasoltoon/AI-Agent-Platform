from agent_core.reliable_executor import ReliableAgentExecutor


def _result(*, tests=True):
    commands = ["python -m pytest -q"] if tests else []
    records = [
        {"step": 1, "tool": "write_file", "ok": True, "result": {"path": "app.py", "content": "print('ok')"}},
        {"step": 2, "tool": "read_file", "ok": True, "result": {"path": "app.py", "content": "print('ok')"}},
    ]
    records.extend({"step": 3 + i, "tool": "terminal", "ok": True, "result": {"command": cmd, "code": 0}} for i, cmd in enumerate(commands))
    return {
        "status": "completed",
        "execution_evidence": {"verified": True, "checks": [{"type": "file_exists", "path": "app.py", "passed": True}]},
        "tool_records": records,
    }


def test_quality_gate_accepts_verified_complex_test_task():
    prompt = """Build a production-quality application. Inspect the repository, implement the feature, add automated tests, run pytest, and verify the final result."""
    accepted, blockers = ReliableAgentExecutor._quality_gate(prompt, _result())
    assert accepted is True
    assert blockers == []


def test_quality_gate_rejects_complex_task_without_tests():
    prompt = """Build a production-quality application. Inspect the repository, implement the feature, add automated tests, run pytest, and verify the final result."""
    accepted, blockers = ReliableAgentExecutor._quality_gate(prompt, _result(tests=False))
    assert accepted is False
    assert "requested_tests_not_executed_successfully" in blockers


def test_continuation_prompt_preserves_original_task_and_failure():
    executor = ReliableAgentExecutor.__new__(ReliableAgentExecutor)
    executor.max_output_chars = 12000
    prompt = executor._continuation_prompt("Build the application and run tests.", 2, "pytest failed", _result())
    assert "Build the application and run tests." in prompt
    assert "pytest failed" in prompt
    assert "Inspect the current workspace" in prompt
