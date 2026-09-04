import pytest

from agent_core.mission_budget import MissionBudget, MissionBudgetState
from agent_core.mission_memory import MissionMemory, MissionMemoryStore


def test_execution_limits_never_exceed_remaining_budget():
    budget = MissionBudget(max_steps=10, max_tool_calls=12, max_output_chars=1000, per_execution_steps=8)
    state = MissionBudgetState(budget)
    state.record_execution({"step_count": 7, "tool_calls": 9, "output_chars": 400})
    limits = state.execution_limits()
    assert limits["max_agent_steps"] == 3
    assert limits["max_output_chars"] == 600
    assert state.reason() is None


def test_budget_blocks_when_a_hard_ceiling_is_reached():
    state = MissionBudgetState(MissionBudget(max_steps=4, max_tool_calls=4, max_output_chars=1000))
    state.record_execution({"step_count": 4, "tool_calls": 1, "output_chars": 10})
    assert state.reason() == "max_steps"
    with pytest.raises(RuntimeError, match="max_steps"):
        state.execution_limits()


def test_budget_state_is_persisted_with_mission_memory():
    store = MissionMemoryStore()
    memory = MissionMemory("m1", "Implement feature")
    memory.mission_budget = {
        "consumed_steps": 21,
        "consumed_tool_calls": 19,
        "consumed_output_chars": 5000,
        "consumed_recovery_attempts": 2,
        "tasks_started": 4,
    }
    store.save(memory)
    restored = store.load("m1")
    assert restored is not None
    assert restored.mission_budget["consumed_steps"] == 21
    assert restored.mission_budget["consumed_recovery_attempts"] == 2
