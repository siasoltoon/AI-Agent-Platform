from agent_core.execution_agent import AgentExecutionError
from agent_core.reliable_executor import ReliableAgentExecutor


def _result(*, tests=True, build=False):
    commands = []
    if build:
        commands.append("python -m py_compile app.py")
    if tests:
        commands.append("python -m pytest -q")
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
    accepted, blockers = ReliableAgentExecutor._quality_gate(prompt, _result(build=True))
    assert accepted is True
    assert blockers == []


def test_quality_gate_rejects_complex_task_without_tests():
    prompt = """Build a production-quality application. Inspect the repository, implement the feature, add automated tests, run pytest, and verify the final result."""
    accepted, blockers = ReliableAgentExecutor._quality_gate(prompt, _result(tests=False, build=True))
    assert accepted is False
    assert "requested_tests_not_executed_successfully" in blockers


def test_quality_gate_rejects_complex_task_without_build():
    prompt = """Build a production-quality application. Inspect the repository, implement the feature, add automated tests, run pytest, and verify the final result."""
    accepted, blockers = ReliableAgentExecutor._quality_gate(prompt, _result(build=False))
    assert accepted is False
    assert "requested_build_or_compile_not_executed_successfully" in blockers


def test_continuation_prompt_preserves_original_task_and_failure():
    executor = ReliableAgentExecutor.__new__(ReliableAgentExecutor)
    executor.max_output_chars = 12000
    prompt = executor._continuation_prompt("Build the application and run tests.", 2, "pytest failed", _result())
    assert "Build the application and run tests." in prompt
    assert "pytest failed" in prompt
    assert "Inspect the current workspace" in prompt


def test_execute_carries_partial_result_into_recovery_prompt(monkeypatch, tmp_path):
    partial = _result(tests=False, build=False)
    prompts = []

    class FakeExecutor:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        def execute(self, prompt):
            prompts.append(prompt)
            type(self).calls += 1
            if type(self).calls == 1:
                raise AgentExecutionError("Agent stopped before producing a verified completion.", partial_result=partial)
            return _result(tests=True, build=True)

    monkeypatch.setattr("agent_core.reliable_executor.AgentExecutor", FakeExecutor)
    executor = ReliableAgentExecutor(
        ollama=object(),
        workspace_root=str(tmp_path),
        max_steps=4,
        max_attempts=2,
    )
    result = executor.execute("Build the application and run pytest.")
    assert result["status"] == "completed"
    assert result["reliability"]["attempts"] == 2
    assert "print('ok')" in prompts[1]
    assert "No usable previous result was returned." not in prompts[1]
