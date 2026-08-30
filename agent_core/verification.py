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
    evidence = result.get("execution_evidence") if isinstance(result, dict) else None
    records = result.get("tool_records") if isinstance(result, dict) else None
    checks = {
        "completed": isinstance(result, dict) and result.get("status") == "completed",
        "evidence_verified": isinstance(evidence, dict) and evidence.get("verified") is True,
        "successful_tool": isinstance(records, list) and any(isinstance(item, dict) and item.get("ok") is True for item in records),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return VerificationResult(verified=not blockers, checks=checks, blockers=blockers)
