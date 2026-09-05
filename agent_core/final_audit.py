"""Cross-component final consistency checks for the production agent platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class AuditResult:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)


class FinalPlatformAudit:
    """Validate cross-component invariants without pretending to execute code."""

    REQUIRED_MODULES = (
        "agent_core.mission_engine",
        "agent_core.mission_memory",
        "agent_core.task_graph",
        "agent_core.context_manager",
        "agent_core.verification",
        "agent_core.adaptive_planner",
        "agent_core.acceptance",
        "agent_core.autonomous_developer",
        "agent_core.execution_fence",
        "backend.storage.execution_ledger",
        "backend.storage.side_effect_ledger",
        "backend.recovery_sweep",
        "backend.safe_task_runner",
    )

    def audit_module_names(self, available_modules: Iterable[str]) -> AuditResult:
        available = set(available_modules)
        checks = {name: name in available for name in self.REQUIRED_MODULES}
        findings = [name for name, present in checks.items() if not present]
        return AuditResult(not findings, checks, findings)

    @staticmethod
    def audit_graph(task_ids: Iterable[str], dependencies: dict[str, set[str]]) -> AuditResult:
        ids = set(task_ids)
        findings = [f"unknown dependency: {task}:{dep}" for task, deps in dependencies.items() for dep in deps if dep not in ids]
        return AuditResult(not findings, {"dependencies_resolved": not findings}, findings)

    @staticmethod
    def audit_completion_contract(*, status: str, verified: bool, blockers: list[str]) -> AuditResult:
        checks = {
            "verified": verified,
            "no_blockers": not blockers,
            "status_consistent": status == "completed" if verified else status != "completed",
        }
        findings = [name for name, passed in checks.items() if not passed]
        return AuditResult(not findings, checks, findings)

    @staticmethod
    def audit_execution_contract(*, execution_state: str, task_status: str, fenced: bool) -> AuditResult:
        """Ensure durable execution state cannot claim completion without fencing."""
        execution_state = str(execution_state).lower()
        task_status = str(task_status).lower()
        checks = {
            "fenced": bool(fenced),
            "committed_implies_completed": execution_state != "committed" or task_status == "completed",
            "completed_implies_committed": task_status != "completed" or execution_state == "committed",
        }
        findings = [name for name, passed in checks.items() if not passed]
        return AuditResult(not findings, checks, findings)
