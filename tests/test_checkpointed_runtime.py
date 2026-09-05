from agent_core.checkpointed_runtime import CheckpointedRuntime
from agent_core.mission_memory import MissionMemory, MissionMemoryStore


class FakeRuntime:
    def __init__(self, result):
        self.result = result

    def execute(self, prompt, *, task_id=None, **kwargs):
        return self.result


def _result():
    return {
        "status": "completed",
        "mission_objective": "Implement feature",
        "execution_evidence": {"verified": True, "tool_calls": 1, "successful_tool_calls": 1},
        "tool_records": [{"tool": "read_file", "ok": True}],
    }


def test_runtime_persists_verified_execution_identity_before_graph_advance():
    store = MissionMemoryStore()
    memory = MissionMemory("m1", "Implement feature")
    store.save(memory)
    runtime = CheckpointedRuntime(FakeRuntime(_result()), store, "m1")

    runtime.execute("work", task_id="m1:implementation:1")

    restored = store.load("m1")
    assert restored is not None
    assert restored.active_task == "implementation"
    assert restored.active_execution_id == "m1:implementation:1"
    assert restored.last_execution["task_id"] == "m1:implementation:1"
    assert restored.checkpoints[-1]["evidence"]["verified"] is True


def test_unverified_execution_is_left_active_for_safe_retry():
    store = MissionMemoryStore()
    memory = MissionMemory("m2", "Implement feature")
    store.save(memory)
    runtime = CheckpointedRuntime(FakeRuntime({"status": "completed", "tool_records": []}), store, "m2")

    runtime.execute("work", task_id="m2:implementation:1")

    restored = store.load("m2")
    assert restored is not None
    assert restored.active_execution_id == "m2:implementation:1"
    assert restored.last_execution == {}
