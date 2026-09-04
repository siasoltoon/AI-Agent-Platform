from agent_core.acceptance import MissionAcceptanceGate
from agent_core.adaptive_planner import AdaptivePlanner, PlanningContext
from agent_core.verification import FailureClass


def test_adaptive_planner_builds_dependency_graph():
    planner = AdaptivePlanner()
    graph = planner.build_graph(PlanningContext("build a bot"), [
        {"task_id": "repo", "title": "Inspect", "objective": "inspect"},
        {"task_id": "impl", "title": "Implement", "objective": "implement", "depends_on": ["repo"]},
    ])
    assert [x.task_id for x in graph.ready()] == ["repo"]


def test_recovery_policy_distinguishes_failures():
    planner = AdaptivePlanner()
    assert planner.recovery_action("pytest assertion failed") == "diagnose_and_repair"
    assert planner.recovery_action("connection timeout") == "retry_with_backoff"
    assert planner.recovery_action("cannot continue") == "stop_and_report_evidence"


def test_acceptance_requires_all_gates():
    gate = MissionAcceptanceGate()
    completed = gate.evaluate(
        mission_status="completed",
        plan_complete=True,
        tests_checked=True,
        final_reviewed=True,
        execution_result={"status": "completed", "execution_evidence": {"verified": True}, "tool_records": [{"ok": True}]},
    )
    assert completed.accepted

    running = gate.evaluate(
        mission_status="running",
        plan_complete=True,
        tests_checked=True,
        final_reviewed=True,
        execution_result={"status": "completed", "execution_evidence": {"verified": True}, "tool_records": [{"ok": True}]},
    )
    assert not running.accepted
    assert "mission_completed" in running.reasons

    blocked = gate.evaluate(mission_status="running", plan_complete=True, tests_checked=False, final_reviewed=True, execution_result={})
    assert not blocked.accepted
    assert "tests_checked" in blocked.reasons


def test_docs_only_acceptance_does_not_require_test_execution():
    gate = MissionAcceptanceGate()
    result = gate.evaluate(
        mission_status="completed",
        plan_complete=True,
        tests_checked=False,
        final_reviewed=True,
        execution_result={
            "mission_objective": "Update the README documentation only",
            "status": "completed",
            "execution_evidence": {"verified": True},
            "tool_records": [{"tool": "read_file", "ok": True}],
        },
    )
    assert result.accepted
    assert result.contract["requires_tests"] is False


def test_implementation_acceptance_requires_test_evidence():
    gate = MissionAcceptanceGate()
    result = gate.evaluate(
        mission_status="completed",
        plan_complete=True,
        tests_checked=False,
        final_reviewed=True,
        execution_result={
            "mission_objective": "Implement a new authentication feature",
            "status": "completed",
            "execution_evidence": {"verified": True},
            "tool_records": [{"tool": "read_file", "ok": True}],
        },
    )
    assert not result.accepted
    assert "tests_checked" in result.reasons
