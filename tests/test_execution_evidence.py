from agent_core.execution_evidence import ExecutionBudget, ExecutionEvidence, enrich_execution_evidence
from agent_core.verification import verify_execution


def test_execution_budget_rejects_invalid_limits():
    for kwargs in (
        {"max_steps": 0},
        {"max_tool_calls": 0},
        {"max_output_chars": 128},
        {"max_runtime_seconds": 0},
        {"max_recovery_attempts": 0},
    ):
        try:
            ExecutionBudget(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid budget accepted: {kwargs}")


def test_execution_evidence_tracks_tools_timeouts_and_ambiguity():
    evidence = ExecutionEvidence()
    evidence.step_count = 3
    evidence.record_tool("terminal", {"ok": True}, output_chars=100)
    evidence.record_tool("terminal", {"ok": False, "timed_out": True}, output_chars=50, truncated=True)
    evidence.record_tool("terminal", {"ok": False, "outcome": "ambiguous"}, output_chars=25)
    evidence.record_retry()
    evidence.record_recovery()

    snapshot = evidence.snapshot()
    assert snapshot["step_count"] == 3
    assert snapshot["tool_calls"] == 3
    assert snapshot["successful_tool_calls"] == 1
    assert snapshot["failed_tool_calls"] == 2
    assert snapshot["timeout_count"] == 1
    assert snapshot["ambiguous_outcomes"] == 1
    assert snapshot["output_chars"] == 175
    assert snapshot["output_truncations"] == 1
    assert snapshot["retries"] == 1
    assert snapshot["recovery_attempts"] == 1
    assert snapshot["tool_outcomes"] == {"terminal": 3}


def test_execution_budget_reports_first_exceeded_boundary():
    budget = ExecutionBudget(max_steps=2, max_tool_calls=3, max_output_chars=1000, max_runtime_seconds=60)
    evidence = ExecutionEvidence()
    evidence.step_count = 2
    assert evidence.check(budget) == "max_steps"


def test_enrich_execution_evidence_uses_real_tool_records():
    result = {
        "status": "completed",
        "steps": [{"step": 1}, {"step": 2}],
        "tool_records": [
            {"step": 1, "tool": "write_file", "ok": True, "result": {"path": "a.txt", "content": "ok"}},
            {"step": 2, "tool": "terminal", "ok": False, "result": {"timed_out": True, "command": "pytest"}, "output_truncated": True},
        ],
        "execution_evidence": {"verified": True},
    }

    enriched = enrich_execution_evidence(result, started_at=ExecutionEvidence().started_at, recovery_attempts=2, retries=1)
    evidence = enriched["execution_evidence"]
    assert evidence["verified"] is True
    assert evidence["step_count"] == 2
    assert evidence["tool_calls"] == 2
    assert evidence["successful_tool_calls"] == 1
    assert evidence["failed_tool_calls"] == 1
    assert evidence["timeout_count"] == 1
    assert evidence["output_truncations"] == 1
    assert evidence["recovery_attempts"] == 2
    assert evidence["retries"] == 1
    assert evidence["tool_outcomes"] == {"write_file": 1, "terminal": 1}


def test_verify_execution_rejects_inconsistent_evidence_counts():
    result = {
        "status": "completed",
        "execution_evidence": {
            "verified": True,
            "tool_calls": 2,
            "successful_tool_calls": 2,
        },
        "tool_records": [{"tool": "read_file", "ok": True}],
    }
    verification = verify_execution(result)
    assert not verification.verified
    assert "evidence_tool_count_matches" in verification.blockers


def test_verify_execution_rejects_policy_violation():
    result = {
        "status": "completed",
        "execution_evidence": {
            "verified": True,
            "policy": {"compliant": False},
        },
        "tool_records": [{"tool": "read_file", "ok": True}],
    }
    verification = verify_execution(result)
    assert not verification.verified
    assert "policy_compliant" in verification.blockers
