from agent_core.verification import verify_execution


def _base(contract_mode: str, authorized_mode: str, *, isolation: dict | None = None) -> dict:
    result = {
        "status": "completed",
        "mission_contract": {"network_access": contract_mode},
        "network_capability": {
            "contract_mode": contract_mode,
            "authorized_mode": authorized_mode,
            "escalation_blocked": True,
        },
        "execution_evidence": {
            "verified": True,
            "tool_calls": 1,
            "successful_tool_calls": 1,
            "security_violations": 0,
        },
        "tool_records": [{"tool": "read_file", "ok": True}],
    }
    if isolation is not None:
        result["network_isolation"] = isolation
    return result


def test_verification_accepts_restricted_capability():
    result = _base("restricted", "restricted")
    verification = verify_execution(result)
    assert verification.verified
    assert verification.checks["network_capability_compliant"] is True


def test_verification_rejects_capability_escalation_in_evidence():
    result = _base("restricted", "allow")
    verification = verify_execution(result)
    assert not verification.verified
    assert "network_capability_compliant" in verification.blockers


def test_verification_rejects_native_contract_without_native_enforcement():
    result = _base("native", "native", isolation={"mode": "native", "enforced": False})
    verification = verify_execution(result)
    assert not verification.verified
    assert "network_capability_compliant" in verification.blockers


def test_verification_accepts_native_contract_with_enforcement():
    result = _base("native", "native", isolation={"mode": "native", "enforced": True})
    verification = verify_execution(result)
    assert verification.verified
