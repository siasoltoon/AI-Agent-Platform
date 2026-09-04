from agent_core.context_manager import MissionContextManager
from agent_core.mission_memory import MissionMemory, MissionMemoryStore
from agent_core.task_graph import GraphTask, TaskGraph
from agent_core.verification import FailureClass, classify_failure, verify_execution


def test_task_graph_dependency_order_and_cycle_detection():
    graph = TaskGraph([
        GraphTask("a", "A", "a"),
        GraphTask("b", "B", "b", {"a"}),
    ])
    assert [task.task_id for task in graph.ready()] == ["a"]
    graph.mark_completed("a")
    assert [task.task_id for task in graph.ready()] == ["b"]


def test_task_graph_rejects_cycles():
    try:
        TaskGraph([GraphTask("a", "A", "a", {"b"}), GraphTask("b", "B", "b", {"a"})])
    except ValueError as exc:
        assert "cycle" in str(exc).lower()
    else:
        raise AssertionError("cycle must be rejected")


def test_memory_checkpoint_round_trip():
    memory = MissionMemory("m1", "build bot")
    memory.checkpoint(step_id="recon", summary="repository inspected")
    memory.record_failure("testing", "pytest timeout")
    memory.record_attempt("testing", 2)
    memory.record_execution({"status": "completed"})
    store = MissionMemoryStore()
    store.save(memory)
    restored = store.load("m1")
    assert restored is not None
    assert restored.checkpoints[0]["step_id"] == "recon"
    assert restored.failures
    assert restored.task_attempts["testing"] == 2
    assert restored.last_execution["status"] == "completed"
    assert restored.last_execution["mission_objective"] == "build bot"


def test_mission_lifecycle_transition_matrix_and_terminal_protection():
    memory = MissionMemory("m2", "harden agent")
    assert memory.status == "pending"
    memory.transition("running")
    memory.transition("interrupted")
    memory.transition("running")
    memory.transition("blocked")
    memory.transition("running")
    memory.transition("completed")
    assert memory.snapshot()["status"] == "completed"
    for status in ("running", "blocked", "cancelled"):
        try:
            memory.transition(status)
        except ValueError as exc:
            assert "transition" in str(exc).lower()
        else:
            raise AssertionError("terminal mission must not be reopened")


def test_invalid_lifecycle_transition_is_rejected():
    memory = MissionMemory("m3", "transition guard")
    try:
        memory.transition("completed")
    except ValueError as exc:
        assert "transition" in str(exc).lower()
    else:
        raise AssertionError("pending mission must not jump directly to completed")


def test_blocked_mission_can_be_resumed():
    memory = MissionMemory("m4", "resume mission", status="blocked")
    memory.transition("running")
    assert memory.status == "running"


def test_invalid_mission_status_is_rejected():
    try:
        MissionMemory("m5", "invalid status", status="unknown")
    except ValueError as exc:
        assert "invalid mission status" in str(exc).lower()
    else:
        raise AssertionError("invalid status must be rejected")


def test_context_is_bounded_and_preserves_critical_mission_fields():
    manager = MissionContextManager(max_chars=220, chunk_chars=50)
    context = manager.build(
        objective="build the production agent",
        active_task="implement durable resume",
        architecture="task graph and runtime",
        memory="m" * 1000,
    )
    assert len(context) <= 220
    assert "[OBJECTIVE]" in context
    assert "build the production agent" in context
    assert "[ACTIVE TASK]" in context
    assert "implement durable resume" in context
    assert all(len(chunk) <= 50 for chunk in manager.chunks(context))


def test_failure_classification_and_execution_verification():
    assert classify_failure("pytest assertion failed") is FailureClass.TEST_FAILURE
    assert classify_failure("connection timeout") is FailureClass.TRANSIENT
    assert verify_execution({"status": "completed", "execution_evidence": {"verified": True}, "tool_records": [{"ok": True}]}).verified
    assert not verify_execution({"status": "completed"}).verified
