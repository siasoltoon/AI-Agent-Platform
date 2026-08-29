import pytest

from task_engine.lifecycle import can_transition, validate_transition


def test_lifecycle_allows_normal_execution_flow():
    assert can_transition("queued", "running")
    assert can_transition("running", "completed")
    assert can_transition("running", "failed")


def test_lifecycle_allows_recovery_and_cancellation():
    assert can_transition("running", "queued")
    assert can_transition("queued", "cancelled")
    assert can_transition("running", "cancelled")


def test_lifecycle_rejects_terminal_state_mutation():
    assert not can_transition("completed", "running")
    assert not can_transition("failed", "queued")
    assert not can_transition("cancelled", "completed")
    with pytest.raises(ValueError, match="Invalid task lifecycle transition"):
        validate_transition("completed", "running")
