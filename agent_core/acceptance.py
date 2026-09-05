"""Final acceptance gate for autonomous developer missions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_core.mission_contract import MissionContract
from agent_core.verification import VerificationResult, verify_execution


@dataclass(frozen=True)
class AcceptanceResult:
    accepted: bool
    reasons: list[str]
    verification: VerificationResult
    contract: dict[str, object] | None = None


class MissionAcceptanceGate:
    """Completion is an evidence-backed state transition, never a model assertion."""

    REQUIRED_CHECKS = ("plan_complete", "tests_checked", "final_reviewed", "execution_verified")

    def evaluate(
        self,
        *,
        mission_status: str,
        plan_complete: bool,
        tests_checked: bool,
        final_reviewed: bool,
        execution_result: dict[str, Any] | None,
    ) -> AcceptanceResult:
        result = execution_result or {}
        verification = verify_execution(result)
        objective = str(result.get("mission_objective", "")).strip()
        contract = MissionContract.from_objective(objective) if objective else None

        checks = {
            "plan_complete": bool(plan_complete),
            "tests_checked": bool(tests_checked) if contract is None or contract.requires_tests else True,
            "final_reviewed": bool(final_reviewed) if contract is None or contract.requires_final_review else True,
            "execution_verified": verification.verified if contract is None or contract.requires_execution_evidence else True,
            "mission_completed": mission_status == "completed",
        }
        if contract is not None and contract.requires_inspection:
            checks["inspection_observed"] = bool(
                verification.checks.get("successful_tool")
                and any(
                    isinstance(record, dict)
                    and record.get("ok") is True
                    and str(record.get("tool", "")).lower() in {
                        "read_file", "list_directory", "search_files", "file_exists", "directory_exists", "terminal"
                    }
                    for record in result.get("tool_records", [])
                    if isinstance(result.get("tool_records"), list)
                )
            )
        if contract is not None and "network_access" in contract.snapshot():
            checks["network_capability_compliant"] = verification.checks.get("network_capability_compliant", False)

        reasons = [name for name, passed in checks.items() if not passed]
        return AcceptanceResult(
            accepted=not reasons,
            reasons=reasons,
            verification=verification,
            contract=contract.snapshot() if contract is not None else None,
        )
