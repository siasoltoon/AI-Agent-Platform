"""Bounded, serializable execution evidence for autonomous missions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import monotonic
from typing import Any


@dataclass(frozen=True)
class ExecutionBudget:
    """Hard ceilings used by orchestration layers to prevent unbounded work."""

    max_steps: int = 64
    max_tool_calls: int = 64
    max_output_chars: int = 262_144
    max_runtime_seconds: float = 900.0
    max_recovery_attempts: int = 6

    def __post_init__(self) -> None:
        if self.max_steps < 1 or self.max_tool_calls < 1 or self.max_output_chars < 256:
            raise ValueError("Execution budgets must be positive and output budget must be at least 256 characters")
        if self.max_runtime_seconds <= 0 or self.max_recovery_attempts < 1:
            raise ValueError("Runtime and recovery budgets must be positive")


@dataclass
class ExecutionEvidence:
    """Compact evidence counters that can survive persistence and recovery."""

    started_at: float = field(default_factory=monotonic)
    step_count: int = 0
    tool_calls: int = 0
    successful_tool_calls: int = 0
    failed_tool_calls: int = 0
    timeout_count: int = 0
    output_chars: int = 0
    output_truncations: int = 0
    retries: int = 0
    recovery_attempts: int = 0
    ambiguous_outcomes: int = 0
    security_violations: int = 0
    tool_outcomes: dict[str, int] = field(default_factory=dict)
    budget_exceeded: str | None = None

    def elapsed_seconds(self) -> float:
        return max(0.0, monotonic() - self.started_at)

    def record_tool(self, tool: str, result: dict[str, Any], *, output_chars: int = 0, truncated: bool = False) -> None:
        self.tool_calls += 1
        name = str(tool)
        self.tool_outcomes[name] = self.tool_outcomes.get(name, 0) + 1
        if result.get("ok") is True:
            self.successful_tool_calls += 1
        else:
            self.failed_tool_calls += 1
        if result.get("timed_out") is True:
            self.timeout_count += 1
        if result.get("ambiguous") is True or result.get("outcome") == "ambiguous":
            self.ambiguous_outcomes += 1
        if _is_security_violation(result):
            self.security_violations += 1
        self.output_chars += max(0, int(output_chars))
        if truncated:
            self.output_truncations += 1

    def record_recovery(self) -> None:
        self.recovery_attempts += 1

    def record_retry(self) -> None:
        self.retries += 1

    def check(self, budget: ExecutionBudget) -> str | None:
        if self.step_count >= budget.max_steps:
            return "max_steps"
        if self.tool_calls >= budget.max_tool_calls:
            return "max_tool_calls"
        if self.output_chars >= budget.max_output_chars:
            return "max_output_chars"
        if self.elapsed_seconds() >= budget.max_runtime_seconds:
            return "max_runtime_seconds"
        if self.recovery_attempts >= budget.max_recovery_attempts:
            return "max_recovery_attempts"
        return None

    def snapshot(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["elapsed_seconds"] = self.elapsed_seconds()
        return payload


def _is_security_violation(record: dict[str, Any]) -> bool:
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


def enrich_execution_evidence(
    result: dict[str, Any],
    *,
    started_at: float,
    recovery_attempts: int = 0,
    retries: int = 0,
) -> dict[str, Any]:
    """Derive durable metrics from real tool records without trusting model claims."""
    records = result.get("tool_records") if isinstance(result.get("tool_records"), list) else []
    evidence = result.get("execution_evidence") if isinstance(result.get("execution_evidence"), dict) else {}
    tool_outcomes: dict[str, int] = {}
    output_chars = 0
    timeouts = 0
    ambiguous = 0
    successful = 0
    failed = 0
    truncations = 0
    security_violations = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        tool = str(record.get("tool", "unknown"))
        tool_outcomes[tool] = tool_outcomes.get(tool, 0) + 1
        if record.get("ok") is True:
            successful += 1
        else:
            failed += 1
        payload = record.get("result")
        if isinstance(payload, dict):
            if payload.get("timed_out") is True:
                timeouts += 1
            if payload.get("ambiguous") is True or payload.get("outcome") == "ambiguous":
                ambiguous += 1
        if record.get("output_truncated") is True:
            truncations += 1
        if _is_security_violation(record):
            security_violations += 1
        output_chars += len(str(payload)) if payload is not None else len(str(record.get("error", "")))

    merged = dict(evidence)
    merged.update({
        "step_count": len(result.get("steps", [])) if isinstance(result.get("steps"), list) else len(records),
        "tool_calls": len(records),
        "successful_tool_calls": successful,
        "failed_tool_calls": failed,
        "timeout_count": timeouts,
        "output_chars": output_chars,
        "output_truncations": truncations,
        "retries": retries,
        "recovery_attempts": recovery_attempts,
        "ambiguous_outcomes": ambiguous,
        "security_violations": security_violations,
        "tool_outcomes": tool_outcomes,
        "elapsed_seconds": max(0.0, monotonic() - started_at),
    })
    result["execution_evidence"] = merged
    return result
