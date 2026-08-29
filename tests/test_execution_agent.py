"""Tests for the autonomous tool-execution loop."""

from pathlib import Path

from agent_core.execution_agent import AgentExecutor


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


def test_agent_executor_accepts_tool_shorthand(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"write_file","args":{"path":"hello.txt","content":"hello world"}}',
        '{"action":"done","summary":"Created hello.txt"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("Create hello.txt")
    assert result["status"] == "completed"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello world"


def test_agent_executor_rejects_workspace_escape(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"tool","tool":"write_file","args":{"path":"../escape.txt","content":"x"}}',
    ])
    try:
        AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("write outside")
    except Exception as exc:
        assert "escapes" in str(exc).lower()
    else:
        raise AssertionError("workspace escape was not rejected")


def test_agent_executor_rejects_unknown_tool(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"tool","tool":"delete_everything","args":{}}',
    ])
    try:
        AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("do something")
    except Exception as exc:
        assert "unknown tool" in str(exc).lower()
    else:
        raise AssertionError("unknown tool was not rejected")


def test_agent_executor_requires_bounded_completion(tmp_path: Path):
    ollama = FakeOllama(['{"action":"tool","tool":"read_file","args":{"path":"missing.txt"}}'] * 3)
    executor = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=3)
    try:
        executor.execute("keep going")
    except Exception as exc:
        assert "maximum execution steps" in str(exc).lower() or "no such file" in str(exc).lower()
    else:
        raise AssertionError("unbounded agent loop did not fail")


def test_agent_executor_rejects_empty_task(tmp_path: Path):
    ollama = FakeOllama([])
    try:
        AgentExecutor(ollama, workspace_root=str(tmp_path)).execute("   ")
    except Exception as exc:
        assert "task cannot be empty" in str(exc).lower()
    else:
        raise AssertionError("empty task was not rejected")
