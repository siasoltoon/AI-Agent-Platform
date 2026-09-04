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


def test_read_only_policy_blocks_write_before_filesystem_mutation(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"write_file","args":{"path":"blocked.txt","content":"must not exist"}}',
        '{"action":"done","summary":"Finished"}',
    ])

    with pytest.raises(AgentExecutionError, match="maximum execution steps") as exc_info:
        AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=2).execute(
            "Perform a read-only audit. Do not modify any files."
        )

    assert not (tmp_path / "blocked.txt").exists()
    partial = exc_info.value.partial_result
    assert partial is not None
    policy = partial["execution_evidence"]["policy"]
    assert policy["read_only"] is True
    assert policy["compliant"] is False
    assert policy["policy_violations"][0]["tool"] == "write_file"


def test_read_only_policy_blocks_terminal_and_survives_recovery(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"terminal","args":{"command":"echo should-not-run"}}',
        '{"action":"write_file","args":{"path":"blocked.txt","content":"must not exist"}}',
        '{"action":"done","summary":"Finished"}',
    ])

    with pytest.raises(AgentExecutionError, match="maximum execution steps") as exc_info:
        AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=3).execute(
            "Inspect only; make no changes."
        )

    assert not (tmp_path / "blocked.txt").exists()
    assert "MISSION POLICY" in ollama.prompts[0]
    assert "terminal execution is not permitted" in ollama.prompts[1]
    assert "tool 'write_file' is not permitted" in ollama.prompts[2]
    partial = exc_info.value.partial_result
    assert partial is not None
    assert partial["execution_evidence"]["policy"]["read_only"] is True
    assert partial["execution_evidence"]["policy"]["compliant"] is False


def test_targeted_write_is_not_misclassified_as_read_only(tmp_path: Path):
    ollama = FakeOllama([
        '{"action":"write_file","args":{"path":"target.txt","content":"expected"}}',
        '{"action":"read_file","args":{"path":"target.txt"}}',
        '{"action":"done","summary":"Created and verified target.txt"}',
    ])

    result = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=3).execute(
        "Create target.txt with exactly: expected. Do not modify or delete any other files."
    )

    assert result["status"] == "completed"
    assert (tmp_path / "target.txt").read_text(encoding="utf-8") == "expected"
    assert result["execution_evidence"]["policy"]["read_only"] is False
    assert result["execution_evidence"]["policy"]["compliant"] is True
