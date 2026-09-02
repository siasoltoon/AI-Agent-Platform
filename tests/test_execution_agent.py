"""Tests for the production autonomous tool-execution loop."""

from pathlib import Path
import pytest
from agent_core.execution_agent import AgentExecutionError, AgentExecutor


class FakeOllama:
    timeout = 10

    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []

    def generate(self, prompt, timeout=None):
        self.prompts.append(prompt)
        return {"response": next(self.responses)}


def test_agent_executor_writes_and_verifies_real_file(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"write_file","tool":"write_file","args":{"path":"hello.txt","content":"hello world"}}',
        '{"action":"read_file","args":{"path":"hello.txt"}}',
        '{"action":"done","summary":"Created and verified hello.txt"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("Create hello.txt")
    assert result["status"] == "completed"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello world"
    assert result["execution_evidence"]["verified"] is True
    assert all(check["passed"] for check in result["execution_evidence"]["checks"])


def test_agent_executor_recovers_from_malformed_action_json(tmp_path: Path):
    ollama = FakeOllama([
        "I will do it now, but this is not JSON.",
        '{"action":"write_file","args":{"path":"recovered.txt","content":"ok"}}',
        '{"action":"done","summary":"Recovered"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=3).execute("Create recovered.txt")
    assert result["status"] == "completed"
    assert (tmp_path / "recovered.txt").read_text(encoding="utf-8") == "ok"
    assert result["steps"][0]["decision_error"] == "Model did not return a valid JSON action."
    assert "ACTION FORMAT ERROR" in ollama.prompts[1]


def test_agent_executor_accepts_file_tool_shorthand_without_explicit_read(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"write_file","args":{"path":"hello.txt","content":"hello world"}}',
        '{"action":"done","summary":"Created hello.txt"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("Create hello.txt")
    assert result["status"] == "completed"


def test_agent_executor_requires_read_for_explicit_verification(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"write_file","args":{"path":"hello.txt","content":"verified"}}',
        '{"action":"done","summary":"Done"}',
        '{"action":"read_file","args":{"path":"hello.txt"}}',
        '{"action":"done","summary":"Created and verified"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=4).execute(
        "Create hello.txt and verify by reading it and checking the exact content."
    )
    assert result["status"] == "completed"
    assert result["steps"][1]["verification"]["verified"] is False
    assert any(c["type"] == "file_content_matches_write" and c["passed"] for c in result["execution_evidence"]["checks"])
    assert "MANDATORY EXACT-CONTENT VERIFICATION PROTOCOL" in ollama.prompts[0]
    assert "MUST now call read_file" in ollama.prompts[1]


def test_agent_executor_requires_read_after_write_even_when_model_tries_done(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"write_file","args":{"path":"agent-evidence.txt","content":"exact"}}',
        '{"action":"done","summary":"Finished"}',
        '{"action":"read_file","args":{"path":"agent-evidence.txt"}}',
        '{"action":"done","summary":"Created, read, and verified exact content"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=4).execute(
        "Create agent-evidence.txt with exactly: exact. Then verify by reading it and confirming the exact content."
    )
    assert result["status"] == "completed"
    assert [record["tool"] for record in result["tool_records"]] == ["write_file", "read_file"]
    assert any(
        check["type"] == "read_content_matches_write"
        and check["path"] == "agent-evidence.txt"
        and check["passed"] is True
        for check in result["execution_evidence"]["checks"]
    )


def test_agent_executor_recovers_from_read_content_mismatch(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"write_file","args":{"path":"recover.txt","content":"expected"}}',
        '{"action":"read_file","args":{"path":"recover.txt"}}',
        '{"action":"done","summary":"Done"}',
        '{"action":"write_file","args":{"path":"recover.txt","content":"expected"}}',
        '{"action":"read_file","args":{"path":"recover.txt"}}',
        '{"action":"done","summary":"Recovered and verified"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=6).execute(
        "Create recover.txt with exactly: expected. Verify by reading it and checking the exact content."
    )
    assert result["status"] == "completed"
    assert result["execution_evidence"]["verified"] is True


def test_agent_executor_supports_multiline_exact_content(tmp_path: Path):
    code = '''class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b

    def multiply(self, a, b):
        return a * b

    def divide(self, a, b):
        if b == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        return a / b
'''
    ollama = FakeOllama([
        '{"action":"write_file","args":{"path":"calculator_demo.py","content":' + __import__("json").dumps(code) + '}}',
        '{"action":"read_file","args":{"path":"calculator_demo.py"}}',
        '{"action":"done","summary":"Created and verified calculator_demo.py"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=3).execute(
        "Create calculator_demo.py exactly as requested and verify by reading it back and checking exact content."
    )
    assert result["status"] == "completed"
    assert (tmp_path / "calculator_demo.py").read_text(encoding="utf-8") == code
    assert result["execution_evidence"]["verified"] is True
    assert any(
        check["type"] == "read_content_matches_write"
        and check["path"] == "calculator_demo.py"
        and check["passed"] is True
        for check in result["execution_evidence"]["checks"]
    )


def test_agent_executor_returns_verified_result_at_step_boundary(tmp_path: Path):
    content = "line one\nline two\nline three\n"
    ollama = FakeOllama([
        '{"action":"write_file","args":{"path":"boundary.txt","content":' + __import__("json").dumps(content) + '}}',
        '{"action":"read_file","args":{"path":"boundary.txt"}}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=2).execute(
        "Create boundary.txt exactly and verify it by reading it back."
    )
    assert result["status"] == "completed"
    assert result["execution_evidence"]["verified"] is True
    assert (tmp_path / "boundary.txt").read_text(encoding="utf-8") == content


def test_agent_executor_preserves_partial_result_on_execution_error(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"write_file","args":{"path":"partial.txt","content":"saved"}}',
        '{"action":"read_file","args":{"path":"partial.txt"}}',
        '{"action":"tool","tool":"unknown_tool","args":{}}',
    ])
    with pytest.raises(AgentExecutionError) as exc_info:
        AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=3).execute(
            "Create partial.txt exactly and verify it by reading it back."
        )
    partial = exc_info.value.partial_result
    assert partial is not None
    assert partial["execution_evidence"]["verified"] is True
    assert [record["tool"] for record in partial["tool_records"]] == ["write_file", "read_file"]


def test_agent_executor_supports_directory_and_search_tools(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"tool","tool":"make_directory","args":{"path":"agent-tool-test"}}',
        '{"action":"tool","tool":"write_file","args":{"path":"agent-tool-test/test.txt","content":"Hello"}}',
        '{"action":"tool","tool":"search_files","args":{"path":"agent-tool-test","pattern":"*.txt"}}',
        '{"action":"done","summary":"Workspace prepared"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("Create a directory and file")
    assert result["status"] == "completed"
    assert "agent-tool-test/test.txt" in result["tool_records"][2]["result"]["matches"]


def test_agent_executor_supports_delete_with_independent_verification(tmp_path: Path):
    (tmp_path / "remove.txt").write_text("remove", encoding="utf-8")
    ollama = FakeOllama([
        '{"action":"tool","tool":"delete_file","args":{"path":"remove.txt"}}',
        '{"action":"tool","tool":"file_exists","args":{"path":"remove.txt"}}',
        '{"action":"done","summary":"Removed and verified"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("Delete remove.txt and verify it is absent")
    assert result["status"] == "completed"
    assert result["execution_evidence"]["verified"] is True
    assert any(c["type"] == "file_absent_after_delete" and c["passed"] for c in result["execution_evidence"]["checks"])


def test_agent_executor_accepts_windows_type_alias(tmp_path: Path):
    (tmp_path / "alias.txt").write_text("alias works", encoding="utf-8")
    ollama = FakeOllama(['{"action":"tool","tool":"type","args":{"path":"alias.txt"}}', '{"action":"done","summary":"Read alias.txt"}'])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=2).execute("Read alias.txt")
    assert result["status"] == "completed"
    assert "alias works" in result["tool_records"][0]["result"]["stdout"]


def test_agent_executor_recovers_from_premature_completion_without_execution(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"done","summary":"Pretended to finish"}',
        '{"action":"write_file","args":{"path":"hello.txt","content":"recovered"}}',
        '{"action":"done","summary":"Recovered after premature completion"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=3).execute("Create hello.txt")
    assert result["status"] == "completed"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "recovered"
    assert result["tool_records"][0]["tool"] == "write_file"
    assert "PREMATURE COMPLETION REJECTED" in ollama.prompts[1]


def test_agent_executor_recovers_from_tool_failure(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"read_file","args":{"path":"missing.txt"}}',
        '{"action":"write_file","args":{"path":"recovered.txt","content":"ok"}}',
        '{"action":"done","summary":"Recovered"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=3).execute("Create recovered.txt")
    assert result["status"] == "completed"
    assert result["tool_records"][0]["ok"] is False
    assert result["tool_records"][1]["ok"] is True


def test_agent_executor_rejects_workspace_escape(tmp_path: Path):
    ollama = FakeOllama(['{"action":"tool","tool":"write_file","args":{"path":"../escape.txt","content":"x"}}'])
    with pytest.raises(AgentExecutionError, match="maximum execution steps|escapes"):
        AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=1).execute("write outside")


def test_agent_executor_rejects_unknown_tool(tmp_path: Path):
    ollama = FakeOllama(['{"action":"tool","tool":"delete_everything","args":{}}'])
    with pytest.raises(AgentExecutionError, match="Unknown tool"):
        AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("do something")


def test_agent_executor_requires_bounded_completion(tmp_path: Path):
    ollama = FakeOllama(['{"action":"tool","tool":"read_file","args":{"path":"missing.txt"}}'] * 3)
    with pytest.raises(Exception, match="maximum execution steps|No such file"):
        AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=3).execute("keep going")


def test_agent_executor_rejects_empty_task(tmp_path: Path):
    with pytest.raises(AgentExecutionError, match="Task cannot be empty"):
        AgentExecutor(FakeOllama([]), workspace_root=str(tmp_path)).execute("   ")
