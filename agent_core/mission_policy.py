from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


_MUTATING_TOOLS = frozenset({"write_file", "make_directory", "copy_file", "move_file", "delete_file"})
_READ_ONLY_TERMINAL = frozenset({"type", "cat", "dir", "ls", "pwd", "where", "findstr", "fc", "tree", "more", "whoami", "hostname", "ver", "date", "time", "git"})


@dataclass(frozen=True)
class MissionPolicy:
    read_only: bool = False

    @classmethod
    def from_task(cls, task: str) -> "MissionPolicy":
        text = (task or "").lower()
        read_only = bool(
            re.search(r"\bread[- ]only\b", text)
            or re.search(r"\bdo not (?:modify|change|write|delete|create)\b", text)
            or re.search(r"\bwithout (?:modifying|changing|writing|deleting|creating)\b", text)
        )
        return cls(read_only=read_only)

    def allows_tool(self, tool: str, args: dict[str, Any] | None = None) -> bool:
        tool = str(tool).strip().lower()
        if not self.read_only:
            return True
        if tool in _MUTATING_TOOLS:
            return False
        if tool == "terminal":
            return self._allows_terminal(args or {})
        return True

    @staticmethod
    def _allows_terminal(args: dict[str, Any]) -> bool:
        command = str(args.get("command", "")).strip()
        if not command:
            return False
        first = command.split()[0].lower().split("\\")[-1]
        return first in _READ_ONLY_TERMINAL

    def describe_violation(self, tool: str, args: dict[str, Any] | None = None) -> str:
        if self.read_only and str(tool).strip().lower() in _MUTATING_TOOLS:
            return f"Mission is read-only; tool '{tool}' is not permitted."
        if self.read_only and str(tool).strip().lower() == "terminal":
            return "Mission is read-only; this terminal command is not permitted."
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
        unauthorized_mutations = [
            record for record in records
            if record.get("ok") is True and record.get("tool") in _MUTATING_TOOLS
        ] if self.read_only else []
        return {
            "read_only": self.read_only,
            "policy_violations": violations,
            "unauthorized_mutations": len(unauthorized_mutations),
            "compliant": not violations and not unauthorized_mutations,
        }
