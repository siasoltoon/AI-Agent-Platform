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
        '{"action":"done","summary":"Created hello.txt"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("Create hello.txt")
    assert result["status"] == "completed"
    assert result["execution_mode"] == "agentic"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello world"
    assert len(result["steps"]) == 2


def test_agent_executor_accepts_tool_shorthand(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"write_file","args":{"path":"hello.txt","content":"hello world"}}',
        '{"action":"done","summary":"Created hello.txt"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("Create hello.txt")
    assert result["status"] == "completed"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello world"


def test_agent_executor_rejects_completion_without_execution(tmp_path: Path):
    ollama = FakeOllama(['{"action":"done","summary":"Pretended to finish"}'])
    with pytest.raises(AgentExecutionError, match="without executing"):
        AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("Create hello.txt")
    assert not (tmp_path / "hello.txt").exists()


def test_agent_executor_rejects_workspace_escape(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"tool","tool":"write_file","args":{"path":"../escape.txt","content":"x"}}',
    ])
    with pytest.raises(AgentExecutionError, match="escapes"):
        AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("write outside")


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
