from agent_core.autonomous_developer import AutonomousDeveloper
from agent_core.mission_memory import MissionMemory, MissionMemoryStore
from agent_core.mission_orchestrator import MissionOrchestrator


class FakeRuntime:
    default_model = "test-model"

    def execute(self, prompt, *, task_id=None, **kwargs):
        return {"status": "completed"}


def test_reconcile_committed_execution_marks_task_completed():
    store = MissionMemoryStore()
    memory = MissionMemory("resume-1", "Implement feature")
    memory.begin_execution("implementation", "resume-1:implementation:2")
    memory.record_execution(
        {
            "task_id": "resume-1:implementation:2",
            "status": "completed",
            "mission_objective": "Implement feature",
            "execution_evidence": {"verified": True, "tool_calls": 1, "successful_tool_calls": 1},
            "tool_records": [{"tool": "read_file", "ok": True}],
        }
    )
    store.save(memory)
    developer = AutonomousDeveloper(FakeRuntime(), memory_store=store)
    orchestrator = MissionOrchestrator(developer)

    orchestrator._reconcile_interrupted_execution("resume-1")

    restored = store.load("resume-1")
    assert restored is not None
    assert "implementation" in restored.completed
    assert restored.active_task == ""
    assert restored.active_execution_id == ""
    assert restored.checkpoints[-1]["evidence"]["reconciled"] is True
