"""Agentic execution loop: turn model decisions into real tool actions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.services.ollama_service import OllamaService
from tool_system.file_tools import ReadFileTool, WriteFileTool
from tool_system.terminal_tools import TerminalTool


class AgentExecutionError(RuntimeError):
    """Raised when the agent cannot produce or execute a valid action."""


class AgentExecutor:
    """Execute coding tasks through a bounded plan/act/observe/verify loop."""

    _TOOLS = {"read_file", "write_file", "terminal"}

    def __init__(
        self,
        ollama: OllamaService,
        workspace_root: str | None = None,
        max_steps: int = 12,
        max_output_chars: int = 12000,
    ) -> None:
        self.ollama = ollama
        self.workspace = Path(workspace_root or Path.cwd()).resolve()
        self.max_steps = max(1, max_steps)
        self.max_output_chars = max(256, max_output_chars)
        self.read_file = ReadFileTool()
        self.write_file = WriteFileTool()
        self.terminal = TerminalTool()

    def _safe_path(self, path: str) -> Path:
        if not path.strip():
            raise AgentExecutionError("Path cannot be empty.")
        candidate = (self.workspace / path).resolve()
        if candidate != self.workspace and self.workspace not in candidate.parents:
            raise AgentExecutionError("Path escapes the configured workspace.")
        return candidate

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        text = text.strip()
        candidates = [text]
        candidates.extend(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE))
        for candidate in candidates:
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                value = json.loads(match.group(0))
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                pass
        raise AgentExecutionError("Model did not return a valid JSON action.")

    @staticmethod
    def _normalize_decision(decision: dict[str, Any]) -> dict[str, Any]:
        action = decision.get("action")
        tool = decision.get("tool")
        if action in AgentExecutor._TOOLS:
            decision = {**decision, "action": "tool", "tool": str(tool or action)}
        return decision

    def _tool(self, name: str, args: dict[str, Any]) -> Any:
        if name == "read_file":
            path = self._safe_path(str(args.get("path", "")))
            return self.read_file.execute(str(path))
        if name == "write_file":
            path = self._safe_path(str(args.get("path", "")))
            path.parent.mkdir(parents=True, exist_ok=True)
            self.write_file.execute(str(path), str(args.get("content", "")))
            return {"ok": True, "path": str(path.relative_to(self.workspace)), "bytes": path.stat().st_size}
        if name == "terminal":
            command = str(args.get("command", "")).strip()
            if not command:
                raise AgentExecutionError("Terminal command cannot be empty.")
            timeout = int(args.get("timeout", 120))
            if timeout < 1 or timeout > 600:
                raise AgentExecutionError("Terminal timeout must be between 1 and 600 seconds.")
            result = self.terminal.execute(command, timeout=timeout)
            return {**result, "command": command}
        raise AgentExecutionError(f"Unknown tool: {name}")

    def _verify_evidence(self, task: str, tool_records: list[dict[str, Any]]) -> dict[str, Any]:
        """Verify completion from observable execution evidence, never from the model's claim alone."""
        successful = [r for r in tool_records if r.get("ok")]
        writes = [r for r in successful if r.get("tool") == "write_file"]
        terminals = [r for r in successful if r.get("tool") == "terminal" and r.get("result", {}).get("code") == 0]

        checks: list[dict[str, Any]] = []
        for record in writes:
            rel = record.get("result", {}).get("path")
            if rel:
                target = self._safe_path(rel)
                checks.append({"type": "file_exists", "path": rel, "passed": target.is_file()})
        for record in terminals:
            checks.append({"type": "terminal_success", "command": record.get("result", {}).get("command"), "passed": True})

        task_lower = task.lower()
        if any(word in task_lower for word in ("create", "write", "make", "generate", "save", "build")):
            passed = bool(writes) and all(c["passed"] for c in checks if c["type"] == "file_exists")
        elif any(word in task_lower for word in ("test", "pytest", "compile", "run")):
            passed = bool(terminals)
        else:
            passed = bool(successful)

        return {"verified": passed, "checks": checks, "successful_tool_actions": len(successful)}

    def execute(self, task: str) -> dict[str, Any]:
        if not task or not task.strip():
            raise AgentExecutionError("Task cannot be empty.")

        system = """You are an autonomous coding agent. You MUST perform the requested task in the workspace, not merely suggest code.

Return exactly one JSON object per turn, with no prose:
{"action":"tool","tool":"read_file|write_file|terminal","args":{...}}
or
{"action":"done","summary":"what was actually completed"}

Rules:
- Inspect relevant existing files before changing them.
- Make real changes with write_file; do not paste proposed code as the final answer.
- Use terminal only for safe project commands such as tests, compilation, formatting, or inspection.
- After changes, run appropriate validation/tests and fix failures.
- Never claim completion unless the requested work was actually performed.
- You MUST execute at least one tool action before returning done.
- A done response is only accepted when observable execution evidence verifies the requested work.
- If a tool fails, inspect the observation, recover, and continue when possible.
- Keep actions small and observable.
"""
        conversation = f"{system}\n\nTASK:\n{task.strip()}\n\nWORKSPACE:\n{self.workspace}"
        actions: list[dict[str, Any]] = []
        tool_records: list[dict[str, Any]] = []

        for step in range(1, self.max_steps + 1):
            response = self.ollama.generate(conversation, timeout=self.ollama.timeout)
            decision = self._normalize_decision(self._extract_json(response.get("response", "")))
            action = decision.get("action")
            actions.append({"step": step, "decision": decision})

            if action == "done":
                evidence = self._verify_evidence(task, tool_records)
                if not tool_records:
                    raise AgentExecutionError("Agent claimed completion without executing a tool action.")
                if not evidence["verified"]:
                    conversation += (
                        "\n\nVERIFICATION FAILED: the completion claim is not supported by observable evidence. "
                        "Perform another tool action to finish and verify the task."
                    )
                    actions[-1]["verification"] = evidence
                    continue
                return {
                    "status": "completed",
                    "execution_mode": "agentic",
                    "summary": str(decision.get("summary", "Task completed.")),
                    "steps": actions,
                    "execution_evidence": evidence,
                    "tool_records": tool_records,
                }

            if action != "tool":
                raise AgentExecutionError("Invalid agent action.")

            tool = str(decision.get("tool", ""))
            args = decision.get("args", {})
            if tool not in self._TOOLS:
                raise AgentExecutionError(f"Unknown tool: {tool}")
            if not isinstance(args, dict):
                raise AgentExecutionError("Tool args must be an object.")

            try:
                result = self._tool(tool, args)
                record = {"step": step, "tool": tool, "ok": True, "result": result}
            except Exception as exc:
                record = {"step": step, "tool": tool, "ok": False, "error_type": type(exc).__name__, "error": str(exc)}
                result = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}

            tool_records.append(record)
            serialized = json.dumps(result, ensure_ascii=False, default=str)
            if len(serialized) > self.max_output_chars:
                serialized = serialized[: self.max_output_chars] + "...<truncated>"
            conversation += (
                f"\n\nOBSERVATION step {step}: tool={tool}\n"
                f"{serialized}\n\nContinue with the next action or return done only after verification."
            )

        raise AgentExecutionError(f"Agent exceeded maximum execution steps ({self.max_steps}).")
