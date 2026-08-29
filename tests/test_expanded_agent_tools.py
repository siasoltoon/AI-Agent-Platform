from pathlib import Path

from agent_core.execution_agent import AgentExecutor


class FakeOllama:
    timeout = 10

    def __init__(self, responses):
        self.responses = iter(responses)

    def generate(self, prompt, timeout=None):
        return {"response": next(self.responses)}


def test_agent_can_check_file_and_list_workspace(tmp_path: Path):
    (tmp_path / "existing.txt").write_text("ok", encoding="utf-8")
    ollama = FakeOllama([
        '{"action":"tool","tool":"file_exists","args":{"path":"existing.txt"}}',
        '{"action":"tool","tool":"list_directory","args":{"path":"."}}',
        '{"action":"done","summary":"Inspected workspace"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=3).execute("Inspect the workspace")
    assert result["status"] == "completed"
    assert result["tool_records"][0]["result"]["exists"] is True
    assert any(item["name"] == "existing.txt" for item in result["tool_records"][1]["result"]["entries"])


def test_agent_can_delete_a_workspace_file(tmp_path: Path):
    path = tmp_path / "remove.txt"
    path.write_text("remove", encoding="utf-8")
    ollama = FakeOllama([
        '{"action":"tool","tool":"delete_file","args":{"path":"remove.txt"}}',
        '{"action":"tool","tool":"file_exists","args":{"path":"remove.txt"}}',
        '{"action":"done","summary":"Removed and verified file is absent"}',
    ])
    result = AgentExecutor(ollama, workspace_root=str(tmp_path), max_steps=3).execute("Delete remove.txt")
    assert result["status"] == "completed"
    assert not path.exists()
    assert result["tool_records"][1]["result"]["exists"] is False
