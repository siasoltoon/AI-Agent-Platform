"""Developer-grade verification and recoverability helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class FailureClass(str, Enum):
    TRANSIENT = "transient"
    VALIDATION = "validation"
    TEST_FAILURE = "test_failure"
    TOOL_FAILURE = "tool_failure"
    ENVIRONMENT = "environment"
    BLOCKING = "blocking"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    checks: dict[str, bool]
    blockers: list[str]

    @property
    def score(self) -> float:
        return sum(self.checks.values()) / len(self.checks) if self.checks else 0.0


def classify_failure(error: BaseException | str) -> FailureClass:
    text = str(error).lower()
    if any(token in text for token in ("timeout", "temporarily", "connection reset", "503", "429")):
        return FailureClass.TRANSIENT
    if any(token in text for token in ("pytest", "test failed", "assertion")):
        return FailureClass.TEST_FAILURE
    if any(token in text for token in ("validation", "invalid", "required")):
        return FailureClass.VALIDATION
    if any(token in text for token in ("tool", "permission denied", "command not found")):
        return FailureClass.TOOL_FAILURE
    if any(token in text for token in ("ollama", "workspace", "no such file", "environment")):
        return FailureClass.ENVIRONMENT
    if any(token in text for token in ("cannot continue", "unsupported", "blocked")):
        return FailureClass.BLOCKING
    return FailureClass.UNKNOWN


def _record_is_security_violation(record: Any) -> bool:
    if not isinstance(record, dict):
        return False
    if record.get("policy_violation") is True or record.get("security_violation") is True:
        return True
    if record.get("error_type") in {"PermissionError", "MissionPolicyViolation", "SecurityViolation"}:
        return True
    payload = record.get("result")
    return isinstance(payload, dict) and (
        payload.get("policy_violation") is True
        or payload.get("security_violation") is True
        or payload.get("error_type") in {"PermissionError", "MissionPolicyViolation", "SecurityViolation"}
    )


_NETWORK_RANK = {"deny": 0, "restricted": 1, "native": 2, "allow": 3}


def _network_isolation(result: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any] | None:
    direct = result.get("network_isolation")
    if isinstance(direct, dict):
        return direct
    embedded = evidence.get("network_isolation")
    if isinstance(embedded, dict):
        return embedded
    for record in result.get("tool_records", []) if isinstance(result.get("tool_records"), list) else []:
        if not isinstance(record, dict) or str(record.get("tool", "")).lower() != "terminal":
            continue
        payload = record.get("result")
        if isinstance(payload, dict) and isinstance(payload.get("network_isolation"), dict):
            return payload["network_isolation"]
    return None


def _network_capability_compliant(result: dict[str, Any], evidence: dict[str, Any]) -> bool:
    contract = result.get("mission_contract")
    if not isinstance(contract, dict) or "network_access" not in contract:
        return True
    expected = str(contract.get("network_access") or "restricted").strip().lower()
    if expected not in _NETWORK_RANK:
        return False
    capability = result.get("network_capability")
    if not isinstance(capability, dict):
        capability = evidence.get("network_capability") if isinstance(evidence.get("network_capability"), dict) else None
    if not isinstance(capability, dict):
        return False
    authorized = str(capability.get("authorized_mode") or "").strip().lower()
    contract_mode = str(capability.get("contract_mode") or expected).strip().lower()
    if contract_mode != expected or authorized not in _NETWORK_RANK:
        return False
    if _NETWORK_RANK[authorized] > _NETWORK_RANK[expected]:
        return False
    if expected == "native":
        isolation = _network_isolation(result, evidence)
        if not isinstance(isolation, dict) or isolation.get("enforced") is not True:
            return False
    return True


def verify_execution(result: dict[str, Any]) -> VerificationResult:
    """Verify completion from independent execution records, not model claims alone."""
    valid_result = isinstance(result, dict)
    evidence = result.get("execution_evidence") if valid_result else None
    records = result.get("tool_records") if valid_result else None
    valid_records = isinstance(records, list)
    record_items = records if valid_records else []
    successful = [item for item in record_items if isinstance(item, dict) and item.get("ok") is True]
    observed_security_violations = sum(1 for item in record_items if _record_is_security_violation(item))

    checks = {
        "completed": valid_result and result.get("status") == "completed",
        "evidence_verified": isinstance(evidence, dict) and evidence.get("verified") is True,
        "successful_tool": bool(valid_records and successful),
        "evidence_tool_count_matches": (
            isinstance(evidence, dict)
            and evidence.get("tool_calls") == len(record_items)
            if isinstance(evidence, dict) and "tool_calls" in evidence
            else valid_records
        ),
        "evidence_success_count_matches": (
            isinstance(evidence, dict)
            and evidence.get("successful_tool_calls") == len(successful)
            if isinstance(evidence, dict) and "successful_tool_calls" in evidence
            else valid_records
        ),
        "policy_compliant": (
            isinstance(evidence, dict)
            and evidence.get("policy", {}).get("compliant") is not False
            if isinstance(evidence, dict) and isinstance(evidence.get("policy", {}), dict)
            else True
        ),
        "security_clean": observed_security_violations == 0 and (
            not isinstance(evidence, dict) or int(evidence.get("security_violations", 0)) == 0
        ),
        "network_capability_compliant": _network_capability_compliant(result, evidence if isinstance(evidence, dict) else {}),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return VerificationResult(verified=not blockers, checks=checks, blockers=blockers)
