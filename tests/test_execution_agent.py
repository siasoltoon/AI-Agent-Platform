"""Tests for the autonomous tool-execution loop."""

from pathlib import Path

import pytest

from agent_core.execution_agent import AgentExecutionError, AgentExecutor


class FakeOllama:
    timeout = 10

    def __init__(self, responses):
        self.responses = iter(responses)

    def generate(self, prompt, timeout=None):
        return {"response": next(self.responses)}


def test_agent_executor_writes_real_file(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"write_file","tool":"write_file","args":{"path":"hello.txt","content":"hello world"}}',
        '{"action":"read_file","args":{"path":"hello.txt"}}',
        '{"action":"done","summary":"Created and verified hello.txt"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("Create hello.txt")
    assert result["status"] == "completed"
    assert result["execution_mode"] == "agentic"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello world"
    assert result["execution_evidence"]["verified"] is True
    assert all(check["passed"] for check in result["execution_evidence"]["checks"])
    assert result["tool_records"][0]["ok"] is True


def test_agent_executor_accepts_tool_shorthand(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"write_file","args":{"path":"hello.txt","content":"hello world"}}',
        '{"action":"done","summary":"Created hello.txt"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("Create hello.txt")
    assert result["status"] == "completed"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello world"


def test_agent_executor_accepts_file_path_alias(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"write_file","args":{"file_path":"agent-test.txt","content":"AI Agent Platform Production Test\\nHello World"}}',
        '{"action":"read_file","args":{"file_path":"agent-test.txt"}}',
        '{"action":"done","summary":"Created and verified agent-test.txt"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path)).execute(
        "Create agent-test.txt with the requested content and verify it."
    )
    assert result["status"] == "completed"
    assert (tmp_path / "agent-test.txt").read_text(encoding="utf-8") == "AI Agent Platform Production Test\nHello World"
    assert result["execution_evidence"]["verified"] is True
    assert any(
        check["type"] == "file_content_matches_write" and check["passed"]
        for check in result["execution_evidence"]["checks"]
    )


def test_agent_executor_rejects_completion_without_execution(tmp_path: Path):
    ollama = FakeOllama(['{"action":"done","summary":"Pretended to finish"}'])
    with pytest.raises(AgentExecutionError, match="without executing"):
        AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("Create hello.txt")
    assert not (tmp_path / "hello.txt").exists()


def test_agent_executor_does_not_trust_done_without_verification(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"read_file","args":{"path":"missing.txt"}}',
        '{"action":"done","summary":"Done anyway"}',
        '{"action":"write_file","args":{"path":"hello.txt","content":"verified"}}',
        '{"action":"done","summary":"Created and verified hello.txt"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=4).execute("Create hello.txt")
    assert result["status"] == "completed"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "verified"
    assert result["execution_evidence"]["verified"] is True
    assert result["steps"][1]["verification"]["verified"] is False


def test_agent_executor_recovers_from_tool_failure(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"read_file","args":{"path":"missing.txt"}}',
        '{"action":"write_file","args":{"path":"recovered.txt","content":"ok"}}',
        '{"action":"done","summary":"Recovered and created recovered.txt"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=3).execute("Create recovered.txt")
    assert result["status"] == "completed"
    assert (tmp_path / "recovered.txt").exists()
    assert result["tool_records"][0]["ok"] is False
    assert result["tool_records"][1]["ok"] is True


def test_agent_executor_rejects_workspace_escape(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"tool","tool":"write_file","args":{"path":"../escape.txt","content":"x"}}',
    ])
    with pytest.raises(AgentExecutionError, match="maximum execution steps|escapes"):
        AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=1).execute("write outside")


def test_agent_executor_rejects_unknown_tool(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"tool","tool":"delete_everything","args":{}}',
    ])
    with pytest.raises(AgentExecutionError, match="Unknown tool"):
        AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("do something")


def test_agent_executor_requires_bounded_completion(tmp_path: Path):
    ollama = FakeOllama(['{"action":"tool","tool":"read_file","args":{"path":"missing.txt"}}'] * 3)
    executor = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=3)
    with pytest.raises(Exception, match="maximum execution steps|No such file"):
        executor.execute("keep going")


def test_agent_executor_rejects_empty_task(tmp_path: Path):
    ollama = FakeOllama([])
    with pytest.raises(AgentExecutionError, match="Task cannot be empty"):
        AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("   ")
