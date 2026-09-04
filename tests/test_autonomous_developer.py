from agent_core.autonomous_developer import AutonomousDeveloper
from agent_core.mission_memory import MissionMemory, MissionMemoryStore


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def execute(self, prompt, task_id=None, metadata=None):
        self.calls.append((task_id, metadata))
        task_id_text = str(task_id or "")
        if ":verification:" in task_id_text:
            records = [{"tool": "terminal", "ok": True, "result": {"command": "pytest -q", "code": 0}}]
        else:
            records = [{"tool": "read_file", "ok": True, "result": {"path": "README.md", "content": "observed"}}]
        return {"result": {"result": {"status": "completed", "execution_evidence": {"verified": True}, "tool_records": records}}}


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


def test_autonomous_developer_resumes_completed_steps_without_repeating_them():
    runtime = FakeRuntime()
    store = MissionMemoryStore()
    memory = store.load("missing")
    assert memory is None

    memory = MissionMemory("m3", "build a bot")
    memory.completed = ["recon", "architecture", "implementation"]
    memory.task_attempts = {"recon": 1, "architecture": 1, "implementation": 2}
    store.save(memory)

    result = AutonomousDeveloper(runtime, memory_store=store).run("m3", "build a bot")
    assert result["status"] == "completed"
    assert [call[0].split(":")[1] for call in runtime.calls] == [
        "integration", "verification", "hardening", "acceptance"
    ]


def test_cancel_pending_mission_is_idempotent_and_terminal():
    store = MissionMemoryStore()
    store.save(MissionMemory("m4", "cancel me"))
    developer = AutonomousDeveloper(FakeRuntime(), memory_store=store)

    first = developer.cancel("m4")
    second = developer.cancel("m4")
    resumed = developer.run("m4", "cancel me")

    assert first["status"] == "cancelled"
    assert first["cancelled"] is True
    assert second["status"] == "cancelled"
    assert resumed["status"] == "cancelled"
    assert developer.runtime.calls == []


def test_cancellation_requested_during_execution_is_honored():
    store = MissionMemoryStore()
    developer = None

    class CancellingRuntime(FakeRuntime):
        def execute(self, prompt, task_id=None, metadata=None):
            self.calls.append((task_id, metadata))
            developer.cancel("m5")
            return {"result": {"result": {"status": "completed", "execution_evidence": {"verified": True}, "tool_records": [{"tool": "read_file", "ok": True}]}}}

    developer = AutonomousDeveloper(CancellingRuntime(), memory_store=store)
    result = developer.run("m5", "cancel during execution")
    assert result["status"] == "cancelled"
    assert result["cancelled"] is True
    assert store.load("m5").status == "cancelled"
