import pytest

from agent_core.checkpointed_runtime import CheckpointedRuntime
from agent_core.mission_memory import MissionMemory, MissionMemoryStore
from agent_core.mission_orchestrator import MissionOrchestrator
from agent_core.autonomous_developer import AutonomousDeveloper


class RaisingRuntime:
    def execute(self, prompt, **kwargs):
        raise RuntimeError("worker connection lost")


def test_checkpointed_runtime_persists_interrupted_outcome():
    store = MissionMemoryStore()
    memory = MissionMemory("outcome-1", "Implement feature")
    store.save(memory)
    runtime = CheckpointedRuntime(RaisingRuntime(), store, "outcome-1")

    with pytest.raises(RuntimeError, match="worker connection lost"):
        runtime.execute("work", task_id="outcome-1:implementation:1")

    restored = store.load("outcome-1")
    assert restored is not None
    assert restored.active_task == "implementation"
    assert restored.active_execution_id == "outcome-1:implementation:1"
    assert restored.active_execution_status == "interrupted"
    assert "worker connection lost" in restored.active_execution_error
    assert restored.checkpoints[-1]["evidence"]["outcome"] == "interrupted"


def test_checkpointed_runtime_persists_ambiguous_outcome():
    class UnverifiedRuntime:
        def execute(self, prompt, **kwargs):
            return {"status": "completed", "tool_records": []}

    store = MissionMemoryStore()
    memory = MissionMemory("outcome-2", "Implement feature")
    store.save(memory)
    runtime = CheckpointedRuntime(UnverifiedRuntime(), store, "outcome-2")

    result = runtime.execute("work", task_id="outcome-2:implementation:1")
    assert result["status"] == "completed"
    restored = store.load("outcome-2")
    assert restored is not None
    assert restored.active_execution_status == "ambiguous"
    assert restored.active_execution_id == "outcome-2:implementation:1"
    assert restored.checkpoints[-1]["evidence"]["outcome"] == "ambiguous"


def test_memory_store_does_not_overwrite_stronger_execution_outcome():
    store = MissionMemoryStore()
    durable = MissionMemory("outcome-3", "Implement feature")
    durable.begin_execution("implementation", "outcome-3:implementation:1")
    durable.mark_execution_interrupted("timeout")
    durable.checkpoint(step_id="implementation", summary="interrupted")
    store.save(durable)

    stale = MissionMemory("outcome-3", "Implement feature")
    stale.begin_execution("implementation", "outcome-3:implementation:1")
    stale.record_failure("implementation", "retrying")
    store.save(stale)

    restored = store.load("outcome-3")
    assert restored is not None
    assert restored.active_execution_status == "interrupted"
    assert restored.active_execution_error == "timeout"
    assert restored.checkpoints[-1]["summary"] == "interrupted"


def test_orchestrator_resume_keeps_ambiguous_execution_uncommitted():
    store = MissionMemoryStore()
    memory = MissionMemory("outcome-4", "Implement feature")
    memory.begin_execution("implementation", "outcome-4:implementation:1")
    memory.mark_execution_ambiguous("missing evidence")
    store.save(memory)

    developer = AutonomousDeveloper(runtime=object(), memory_store=store)
    orchestrator = MissionOrchestrator(developer)
    orchestrator._reconcile_interrupted_execution("outcome-4")

    restored = store.load("outcome-4")
    assert restored is not None
    assert restored.active_execution_id == "outcome-4:implementation:1"
    assert restored.active_execution_status == "ambiguous"
    assert "implementation" not in restored.completed
    assert restored.checkpoints[-1]["evidence"]["safe_to_advance"] is False
