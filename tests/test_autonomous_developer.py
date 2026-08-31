from agent_core.autonomous_developer import AutonomousDeveloper


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def execute(self, prompt, task_id=None, metadata=None):
        self.calls.append((task_id, metadata))
        return {"result": {"result": {"status": "completed", "execution_evidence": {"verified": True}, "tool_records": [{"ok": True}]}}}


def test_autonomous_developer_completes_dependency_ordered_mission():
    runtime = FakeRuntime()
    result = AutonomousDeveloper(runtime).run("m1", "build a bot")
    assert result["status"] == "completed"
    assert result["verified"] is True
    assert [call[0].split(":")[1] for call in runtime.calls] == [
        "recon", "architecture", "implementation", "integration", "verification", "hardening", "acceptance"
    ]


def test_autonomous_developer_retries_and_blocks_after_verification_failure():
    class BadRuntime(FakeRuntime):
        def execute(self, prompt, task_id=None, metadata=None):
            self.calls.append((task_id, metadata))
            return {"result": {"result": {"status": "completed", "execution_evidence": {"verified": False}, "tool_records": []}}}

    result = AutonomousDeveloper(BadRuntime()).run("m2", "build a bot", max_retries=2)
    assert result["status"] == "blocked"
    assert result["task"] == "recon"
