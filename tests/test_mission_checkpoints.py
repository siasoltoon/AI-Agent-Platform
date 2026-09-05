import pytest

from agent_core.mission_memory import MissionMemory, MissionMemoryStore


def test_execution_checkpoint_is_monotonic_and_resumable():
    store = MissionMemoryStore()
    memory = MissionMemory("checkpoint-1", "Implement feature")
    memory.begin_execution("implementation", "checkpoint-1:implementation:1")
    store.save(memory)

    restored = store.load("checkpoint-1")
    assert restored is not None
    assert restored.active_task == "implementation"
    assert restored.active_execution_id == "checkpoint-1:implementation:1"

    result = {"status": "completed", "mission_objective": "Implement feature", "execution_evidence": {"verified": True}, "tool_records": [{"tool": "read_file", "ok": True}]}
    restored.commit_execution(task_id="implementation", execution_id="checkpoint-1:implementation:1", result=result)
    store.save(restored)

    resumed = store.load("checkpoint-1")
    assert resumed is not None
    assert resumed.last_execution["status"] == "completed"
    assert resumed.checkpoint_sequence == 1
    assert resumed.checkpoints[-1]["evidence"]["execution_id"] == "checkpoint-1:implementation:1"


def test_execution_checkpoint_rejects_wrong_execution_identity():
    memory = MissionMemory("checkpoint-2", "Implement feature")
    memory.begin_execution("implementation", "checkpoint-2:implementation:1")
    with pytest.raises(ValueError, match="does not match"):
        memory.commit_execution(
            task_id="implementation",
            execution_id="checkpoint-2:implementation:2",
            result={"status": "completed"},
        )
