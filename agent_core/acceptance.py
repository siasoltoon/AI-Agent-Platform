"""Final acceptance gate for autonomous developer missions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_core.verification import VerificationResult, verify_execution


@dataclass(frozen=True)
class AcceptanceResult:
    accepted: bool
    reasons: list[str]
    verification: VerificationResult


class MissionAcceptanceGate:
    """Completion is an evidence-backed state transition, never a model assertion."""

    REQUIRED_CHECKS = ("plan_complete", "tests_checked", "final_reviewed", "execution_verified")

    def evaluate(self, *, mission_status: str, plan_complete: bool, tests_checked: bool,
                 final_reviewed: bool, execution_result: dict[str, Any] | None) -> AcceptanceResult:
        verification = verify_execution(execution_result or {})
        checks = {
            "plan_complete": bool(plan_complete),
            "tests_checked": bool(tests_checked),
            "final_reviewed": bool(final_reviewed),
            "execution_verified": verification.verified,
        }
        reasons = [name for name, passed in checks.items() if not passed]
        if mission_status == "blocked":
            reasons.append("mission_blocked")
        return AcceptanceResult(accepted=not reasons, reasons=reasons, verification=verification)
