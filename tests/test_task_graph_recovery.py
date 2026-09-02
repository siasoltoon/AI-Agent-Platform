from agent_core.adaptive_planner import AdaptivePlanner
from agent_core.task_graph import GraphTask, TaskGraph


def test_recovery_expansion_runs_diagnosis_repair_then_original_task():
    graph = TaskGraph([GraphTask("work", "Work", "Do work")])
    task = graph.tasks["work"]
    task.attempts = 1

    repairs = AdaptivePlanner().expand_after_failure(graph, "work", RuntimeError("test failure"))

    assert [item.task_id for item in repairs] == ["work:diagnose:2", "work:repair:2"]
    assert graph.tasks["work"].depends_on == {"work:repair:2"}
    assert [item.task_id for item in graph.ready()] == ["work:diagnose:2"]

    graph.mark_completed("work:diagnose:2")
    assert [item.task_id for item in graph.ready()] == ["work:repair:2"]

    graph.mark_completed("work:repair:2")
    assert [item.task_id for item in graph.ready()] == ["work"]


def test_task_graph_rejects_invalid_new_dependency_without_corrupting_state():
    graph = TaskGraph([GraphTask("a", "A", "A")])

    try:
        graph.add_dependency("a", "missing")
    except KeyError:
        pass
    else:
        raise AssertionError("Expected unknown dependency to be rejected")

    assert graph.tasks["a"].depends_on == set()
