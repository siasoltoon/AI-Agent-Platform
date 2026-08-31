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
    store = MissionMemoryStore()
    store.save(memory)
    restored = store.load("m1")
    assert restored is not None
    assert restored.checkpoints[0]["step_id"] == "recon"
    assert restored.failures


def test_context_is_bounded():
    manager = MissionContextManager(max_chars=100, chunk_chars=50)
    context = manager.build(objective="x" * 500)
    assert len(context) <= 100
    assert all(len(chunk) <= 50 for chunk in manager.chunks(context))


def test_failure_classification_and_execution_verification():
    assert classify_failure("pytest assertion failed") is FailureClass.TEST_FAILURE
    assert classify_failure("connection timeout") is FailureClass.TRANSIENT
    assert verify_execution({"status": "completed", "execution_evidence": {"verified": True}, "tool_records": [{"ok": True}]}).verified
    assert not verify_execution({"status": "completed"}).verified
