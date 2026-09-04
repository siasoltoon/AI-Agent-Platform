from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


_MUTATING_TOOLS = frozenset({"write_file", "make_directory", "copy_file", "move_file", "delete_file"})


@dataclass(frozen=True)
class MissionPolicy:
    """Machine-enforced constraints derived from the original mission."""

    read_only: bool = False

    @classmethod
    def from_task(cls, task: str) -> "MissionPolicy":
        text = (task or "").lower()
        read_only_patterns = (
            r"\bread[- ]only\b",
            r"\bdo not (?:modify|change|write|delete|create|alter)\b",
            r"\bdon['’]t (?:modify|change|write|delete|create|alter)\b",
            r"\bwithout (?:modifying|changing|writing|deleting|creating|altering|making changes)\b",
            r"\bno changes?\b",
            r"\bwithout making changes\b",
            r"\b(?:inspect|inspection|audit|review) only\b",
        )
        return cls(read_only=any(re.search(pattern, text) for pattern in read_only_patterns))

    def allows_tool(self, tool: str, args: dict[str, Any] | None = None) -> bool:
        if not self.read_only:
            return True
        normalized = str(tool).strip().lower()
        # Terminal is denied completely in read-only mode. A shell command cannot
        # be made safely read-only by checking only its first token (e.g. git commit).
        return normalized not in _MUTATING_TOOLS and normalized != "terminal"

    def describe_violation(self, tool: str, args: dict[str, Any] | None = None) -> str:
        normalized = str(tool).strip().lower()
        if self.read_only and normalized == "terminal":
            return "Mission is read-only; terminal execution is not permitted."
        if self.read_only and normalized in _MUTATING_TOOLS:
            return f"Mission is read-only; tool '{tool}' is not permitted."
        return "Tool is not permitted by the mission policy."

    def evidence(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        violations = [
            {
                "step": record.get("step"),
                "tool": record.get("tool"),
                "error": record.get("error") or record.get("result", {}).get("error"),
            }
            for record in records
            if record.get("policy_violation")
        ]
        unauthorized_mutations = sum(
            1
            for record in records
            if record.get("ok") is True and record.get("tool") in _MUTATING_TOOLS
        ) if self.read_only else 0
        return {
            "read_only": self.read_only,
            "policy_violations": violations,
            "unauthorized_mutations": unauthorized_mutations,
            "compliant": not violations and unauthorized_mutations == 0,
        }
