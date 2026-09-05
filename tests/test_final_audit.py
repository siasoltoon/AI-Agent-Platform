from agent_core.acceptance import MissionAcceptanceGate
from agent_core.final_audit import FinalPlatformAudit


def test_required_modules_audit():
    audit = FinalPlatformAudit()
    result = audit.audit_module_names(audit.REQUIRED_MODULES)
    assert result.passed


def test_graph_dependency_audit():
    result = FinalPlatformAudit.audit_graph(["a", "b"], {"b": {"a"}})
    assert result.passed
    bad = FinalPlatformAudit.audit_graph(["a"], {"a": {"missing"}})
    assert not bad.passed


def test_completion_contract():
    audit = FinalPlatformAudit()
    assert audit.audit_completion_contract(status="completed", verified=True, blockers=[]).passed
    assert not audit.audit_completion_contract(status="completed", verified=False, blockers=[]).passed


def test_execution_contract():
    assert FinalPlatformAudit.audit_execution_contract(execution_state="committed", task_status="completed", fenced=True).passed
    assert not FinalPlatformAudit.audit_execution_contract(execution_state="committed", task_status="running", fenced=True).passed
    assert not FinalPlatformAudit.audit_execution_contract(execution_state="committed", task_status="completed", fenced=False).passed
    assert not FinalPlatformAudit.audit_execution_contract(execution_state="running", task_status="completed", fenced=True).passed


def test_acceptance_requires_terminal_completed_status():
    gate = MissionAcceptanceGate()
    result = gate.evaluate(
        mission_status="running",
        plan_complete=True,
        tests_checked=True,
        final_reviewed=True,
        execution_result={
            "status": "completed",
            "execution_evidence": {"verified": True},
            "tool_records": [{"ok": True}],
        },
    )
    assert not result.accepted
    assert "mission_completed" in result.reasons


def test_acceptance_allows_verified_completed_mission():
    gate = MissionAcceptanceGate()
    result = gate.evaluate(
        mission_status="completed",
        plan_complete=True,
        tests_checked=True,
        final_reviewed=True,
        execution_result={
            "status": "completed",
            "execution_evidence": {"verified": True},
            "tool_records": [{"ok": True}],
        },
    )
    assert result.accepted
