"""Self-repairing orchestration layer for autonomous coding tasks.

The reliable executor keeps a mission alive until the observable completion
contract passes. Failed actions, incomplete work and weak evidence become
continuation prompts instead of premature success.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agent_core.execution_agent import AgentExecutionError, AgentExecutor
from backend.services.ollama_service import OllamaService


class ReliableAgentExecutor:
    """Run an agent task with bounded self-repair and completion-quality gates."""

    MAX_ATTEMPTS = 6
    DEFAULT_AGENT_STEPS = 64

    def __init__(
        self,
        ollama: OllamaService,
        workspace_root: str | None = None,
        max_steps: int = DEFAULT_AGENT_STEPS,
        max_attempts: int = MAX_ATTEMPTS,
        max_output_chars: int = 12000,
    ) -> None:
        self.ollama = ollama
        self.workspace_root = workspace_root
        self.max_steps = max(1, min(int(max_steps), 128))
        self.max_attempts = max(1, min(int(max_attempts), self.MAX_ATTEMPTS))
        self.max_output_chars = max(256, int(max_output_chars))

    @staticmethod
    def _records(result: dict[str, Any]) -> list[dict[str, Any]]:
        records = result.get("tool_records")
        return records if isinstance(records, list) else []

    @staticmethod
    def _evidence(result: dict[str, Any]) -> dict[str, Any]:
        evidence = result.get("execution_evidence")
        return evidence if isinstance(evidence, dict) else {}

    @staticmethod
    def _successful(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [record for record in records if isinstance(record, dict) and record.get("ok") is True]

    @staticmethod
    def _command(record: dict[str, Any]) -> str:
        payload = record.get("result")
        return str(payload.get("command", "")) if isinstance(payload, dict) else ""

    @staticmethod
    def _remove_non_instructional_test_mentions(prompt: str) -> str:
        """Remove test-like words that occur only as filenames or path fragments."""
        text = re.sub(r"(?i)\b[\w./\\-]*test[\w./\\-]*\.(?:txt|md|rst|log|json|ya?ml|toml|ini|cfg|conf)\b", " ", prompt)
        text = re.sub(r"(?i)\b(?:test|tests)[\w./\\-]*\.(?:py|js|jsx|ts|tsx|sh|bat|ps1)\b", " ", text)
        return text

    @classmethod
    def _quality_requirements(cls, prompt: str) -> dict[str, bool]:
        lower = cls._remove_non_instructional_test_mentions(prompt).lower()
        return {
            "tests": bool(re.search(
                r"\b(?:run|execute|perform|write|create|add|build|pass|fix|verify|validate)\s+(?:the\s+)?(?:automated\s+)?(?:tests?|test suite)\b"
                r"|\b(?:pytest|test suite|automated tests|unit tests|integration tests)\b"
                r"|\btests?\s+(?:must|should|need to)\s+(?:pass|run|execute)\b",
                lower,
            )),
            "build": bool(re.search(r"\b(build (?:the|this|project|application|frontend|backend|artifact)|compile|compilation|npm run build)\b", lower)),
            "inspect": bool(re.search(r"\b(inspect|review|audit)\b", lower)),
            "verify": bool(re.search(r"\b(verify|verification|validate|validation|check)\b", lower)),
            "documentation": "readme" in lower or "documentation" in lower,
        }

    @classmethod
    def _quality_gate(cls, prompt: str, result: dict[str, Any]) -> tuple[bool, list[str]]:
        records = cls._records(result)
        successful = cls._successful(records)
        evidence = cls._evidence(result)
        requirements = cls._quality_requirements(prompt)
        blockers: list[str] = []

        if result.get("status") != "completed":
            blockers.append("agent_status_not_completed")
        if evidence.get("verified") is not True:
            blockers.append("execution_evidence_not_verified")
        if not successful:
            blockers.append("no_successful_tool_action")

        tools = {str(record.get("tool", "")).lower() for record in successful}
        terminal_commands = [
            cls._command(record).lower()
            for record in successful
            if str(record.get("tool", "")).lower() == "terminal"
            or str(record.get("tool", "")).lower() in {"pytest", "python", "py", "pip", "npm", "node", "ruff", "mypy", "black", "vite"}
        ]

        if requirements["tests"] and not any(
            "pytest" in command
            or ("test" in command and any(token in command for token in ("python", "py", "npm", "yarn", "pnpm", "cargo", "go")))
            for command in terminal_commands
        ):
            blockers.append("requested_tests_not_executed_successfully")

        if requirements["build"] and not any(
            any(token in command for token in ("build", "compile", "py_compile"))
            for command in terminal_commands
        ):
            blockers.append("requested_build_or_compile_not_executed_successfully")

        if requirements["inspect"] and not (tools & {"read_file", "list_directory", "search_files", "file_exists", "directory_exists", "terminal"}):
            blockers.append("requested_inspection_not_observed")

        return not blockers, blockers

    def _continuation_prompt(self, prompt: str, attempt: int, error: str, result: dict[str, Any] | None) -> str:
        summary = ""
        if result:
            evidence = self._evidence(result)
            records = self._records(result)
            recent = records[-12:]
            summary = json.dumps(
                {"evidence": evidence, "recent_tool_records": recent},
                ensure_ascii=False,
                default=str,
            )
            if len(summary) > self.max_output_chars:
                summary = summary[: self.max_output_chars] + "...<truncated>"

        return f"""Continue the existing autonomous coding mission. This is recovery attempt {attempt}.

ORIGINAL MISSION:
{prompt}

PREVIOUS ATTEMPT PROBLEM:
{error}

PREVIOUS OBSERVATIONS:
{summary or "No usable previous result was returned."}

MISSION CONTINUATION CONTRACT:
1. Inspect the current workspace first; do not restart or overwrite correct work.
2. Treat the original mission as authoritative. Preserve every requirement, file, command, constraint and acceptance criterion.
3. Identify what is already complete and what is still missing.
4. Repair the root cause of the previous failure before proceeding.
5. Continue implementing until the requested functionality is actually present.
6. Run requested tests/builds/checks and repair failures rather than reporting them.
7. Perform a final audit of the resulting files and behavior using concrete tools.
8. If a verification read or test disproves the result, repair it and verify again.
9. Do not return done merely because files were created or a previous step succeeded.
10. Return only the required JSON action format.

The goal of this recovery attempt is to finish the ORIGINAL MISSION, not to explain why it is difficult."""

    def execute(self, prompt: str) -> dict[str, Any]:
        if not prompt or not prompt.strip():
            raise AgentExecutionError("Task prompt cannot be empty.")

        original = prompt.strip()
        last_error = ""
        last_result: dict[str, Any] | None = None
        attempt_records: list[dict[str, Any]] = []

        for attempt in range(1, self.max_attempts + 1):
            effective_prompt = original if attempt == 1 else self._continuation_prompt(original, attempt, last_error, last_result)
            executor = AgentExecutor(
                self.ollama,
                workspace_root=self.workspace_root,
                max_steps=self.max_steps,
                max_output_chars=self.max_output_chars,
            )
            try:
                result = executor.execute(effective_prompt)
                last_result = result
                accepted, blockers = self._quality_gate(original, result)
                attempt_records.append({"attempt": attempt, "accepted": accepted, "blockers": blockers})
                if accepted:
                    result["reliability"] = {
                        "attempts": attempt,
                        "self_repaired": attempt > 1,
                        "quality_gate": "passed",
                        "attempt_history": attempt_records,
                    }
                    return result
                last_error = "Completion quality gate rejected the attempt: " + ", ".join(blockers)
            except Exception as exc:
                partial = getattr(exc, "partial_result", None)
                if isinstance(partial, dict):
                    last_result = partial
                last_error = f"{type(exc).__name__}: {exc}"
                attempt_records.append({"attempt": attempt, "accepted": False, "error": last_error})

        raise AgentExecutionError(
            f"Agent could not complete the task after {self.max_attempts} self-repair attempts. "
            f"Last failure: {last_error}"
        )
