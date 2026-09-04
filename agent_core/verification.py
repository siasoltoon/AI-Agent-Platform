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


def verify_execution(result: dict[str, Any]) -> VerificationResult:
    """Verify completion from independent execution records, not model claims alone."""
    valid_result = isinstance(result, dict)
    evidence = result.get("execution_evidence") if valid_result else None
    records = result.get("tool_records") if valid_result else None
    valid_records = isinstance(records, list)
    record_items = records if valid_records else []
    successful = [item for item in record_items if isinstance(item, dict) and item.get("ok") is True]

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
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return VerificationResult(verified=not blockers, checks=checks, blockers=blockers)
