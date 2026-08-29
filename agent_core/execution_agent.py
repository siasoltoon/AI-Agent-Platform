"""Agentic execution loop: turn model decisions into real tool actions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.services.ollama_service import OllamaService
from tool_system.file_tools import (
    DeleteFileTool,
    FileExistsTool,
    ListDirectoryTool,
    ReadFileTool,
    WriteFileTool,
)
from tool_system.terminal_tools import TerminalTool


class AgentExecutionError(RuntimeError):
    """Raised when the agent cannot produce or execute a valid action."""


class AgentExecutor:
    """Execute coding tasks through a bounded plan/act/observe/verify loop."""

    _TOOLS = {
        "read_file",
        "write_file",
        "file_exists",
        "list_directory",
        "delete_file",
        "terminal",
    }
    _TERMINAL_ALIASES = {
        "type", "cat", "dir", "ls", "pwd", "where", "findstr", "fc", "tree", "more", "echo",
        "python", "py", "pytest", "pip", "pip3", "git", "uvicorn", "ruff", "black", "mypy",
        "node", "npm", "npm.cmd", "npx", "vite", "yarn", "pnpm", "dotnet", "java", "javac", "go", "cargo", "rustc",
    }

    def __init__(self, ollama: OllamaService, workspace_root: str | None = None, max_steps: int = 12, max_output_chars: int = 12000) -> None:
        self.ollama = ollama
        self.workspace = Path(workspace_root or Path.cwd()).resolve()
        self.max_steps = max(1, max_steps)
        self.max_output_chars = max(256, max_output_chars)
        self.read_file = ReadFileTool()
        self.write_file = WriteFileTool()
        self.file_exists = FileExistsTool()
        self.list_directory = ListDirectoryTool()
        self.delete_file = DeleteFileTool()
        self.terminal = TerminalTool()

    def _safe_path(self, path: str) -> Path:
        if not str(path).strip():
            raise AgentExecutionError("Path cannot be empty.")
        candidate = (self.workspace / str(path)).resolve()
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

    @classmethod
    def _normalize_decision(cls, decision: dict[str, Any]) -> dict[str, Any]:
        action = str(decision.get("action", ""))
        tool = str(decision.get("tool", ""))
        if action in cls._TOOLS:
            return {**decision, "action": "tool", "tool": tool or action}
        if action in cls._TERMINAL_ALIASES:
            return {**decision, "action": "tool", "tool": action}
        if tool in cls._TERMINAL_ALIASES:
            return {**decision, "action": "tool", "tool": tool}
        return decision

    @staticmethod
    def _arg(args: dict[str, Any], *names: str, default: Any = "") -> Any:
        for name in names:
            value = args.get(name)
            if value is not None and str(value).strip():
                return value
        return default

    def _alias_command(self, name: str, args: dict[str, Any]) -> str:
        path = str(self._arg(args, "path", "file_path", "filepath", default="")).strip()
        quoted = f'"{self._safe_path(path)}"' if path else ""
        if name in {"type", "cat"}:
            return f"type {quoted}".strip()
        if name in {"dir", "ls", "pwd", "where", "tree", "more"}:
            return f"{name} {quoted}".strip()
        if name == "findstr":
            pattern = str(self._arg(args, "pattern", "query", "text", default=""))
            if not pattern or not path:
                raise AgentExecutionError("findstr requires pattern/query and path.")
            return f'findstr /N "{pattern}" {quoted}'
        if name == "fc":
            other = str(self._arg(args, "other", "compare", "path2", default=""))
            if not other or not path:
                raise AgentExecutionError("fc requires path and compare/path2.")
            return f'fc {quoted} "{self._safe_path(other)}"'
        if name == "echo":
            text = str(self._arg(args, "text", "message", "content", default=""))
            return f"echo {text}".strip()
        command = str(self._arg(args, "command", "cmd", default=name)).strip()
        return command if command.split()[0].lower() == name.lower() else f"{name} {command}".strip()

    def _tool(self, name: str, args: dict[str, Any]) -> Any:
        if name == "read_file":
            path = self._safe_path(str(self._arg(args, "path", "file_path", "filepath")))
            content = self.read_file.execute(str(path))
            return {"ok": True, "path": str(path.relative_to(self.workspace)), "content": content}
        if name == "write_file":
            path = self._safe_path(str(self._arg(args, "path", "file_path", "filepath")))
            content = str(self._arg(args, "content", "text", "body"))
            self.write_file.execute(str(path), content)
            return {"ok": True, "path": str(path.relative_to(self.workspace)), "bytes": path.stat().st_size, "content": content}
        if name == "file_exists":
            path = self._safe_path(str(self._arg(args, "path", "file_path", "filepath")))
            return {"ok": True, "path": str(path.relative_to(self.workspace)), "exists": self.file_exists.execute(str(path))["exists"]}
        if name == "list_directory":
            path = self._safe_path(str(self._arg(args, "path", "directory", default=".")))
            result = self.list_directory.execute(str(path))
            result["path"] = str(path.relative_to(self.workspace)) if path != self.workspace else "."
            return {"ok": True, **result}
        if name == "delete_file":
            path = self._safe_path(str(self._arg(args, "path", "file_path", "filepath")))
            return self.delete_file.execute(str(path))

        command = str(self._arg(args, "command", "cmd", default="")).strip() if name == "terminal" else self._alias_command(name, args)
        if not command:
            raise AgentExecutionError("Terminal command cannot be empty.")
        timeout = int(args.get("timeout", 120))
        if timeout < 1 or timeout > 600:
            raise AgentExecutionError("Terminal timeout must be between 1 and 600 seconds.")
        return {**self.terminal.execute(command, timeout=timeout), "command": command}

    def _verify_evidence(self, task: str, tool_records: list[dict[str, Any]]) -> dict[str, Any]:
        successful = [r for r in tool_records if r.get("ok")]
        writes = [r for r in successful if r.get("tool") == "write_file"]
        reads = [r for r in successful if r.get("tool") == "read_file"]
        terminals = [r for r in successful if r.get("result", {}).get("code") == 0 and r.get("tool") in ("terminal", *self._TERMINAL_ALIASES)]
        checks: list[dict[str, Any]] = []
        written_by_path: dict[str, str] = {}
        for record in writes:
            result = record.get("result", {})
            rel, content = result.get("path"), result.get("content")
            if rel:
                exists = self._safe_path(str(rel)).is_file()
                checks.append({"type": "file_exists", "path": rel, "passed": exists})
                if exists and isinstance(content, str):
                    written_by_path[str(rel)] = content
        for record in reads:
            result = record.get("result", {})
            rel, content = result.get("path"), result.get("content")
            if rel:
                exists = self._safe_path(str(rel)).is_file()
                checks.append({"type": "file_exists", "path": rel, "passed": exists})
                if exists and str(rel) in written_by_path:
                    checks.append({"type": "file_content_matches_write", "path": rel, "passed": content == written_by_path[str(rel)]})
        for record in terminals:
            checks.append({"type": "terminal_success", "command": record.get("result", {}).get("command"), "passed": True})
        task_lower = task.lower()
        if any(word in task_lower for word in ("create", "write", "make", "generate", "save", "build")):
            file_checks = [c for c in checks if c["type"] in ("file_exists", "file_content_matches_write")]
            passed = bool(writes) and bool(file_checks) and all(c["passed"] for c in file_checks)
        elif any(word in task_lower for word in ("test", "pytest", "compile", "run")):
            passed = bool(terminals)
        else:
            passed = bool(successful)
        return {"verified": passed, "checks": checks, "successful_tool_actions": len(successful)}

    def execute(self, task: str) -> dict[str, Any]:
        if not task or not task.strip():
            raise AgentExecutionError("Task cannot be empty.")
        system = """You are an autonomous coding agent. Perform the requested task in the workspace.
Return exactly one JSON object per turn:
{"action":"tool","tool":"TOOL_NAME","args":{...}} or {"action":"done","summary":"..."}
Available tools: read_file, write_file, file_exists, list_directory, delete_file, terminal, type, cat, dir, ls, pwd, where, findstr, fc, tree, more, echo, python, py, pytest, pip, git, uvicorn, ruff, black, mypy, node, npm, npx, vite, yarn, pnpm, dotnet, java, javac, go, cargo, rustc.
Use dedicated workspace tools for file operations and verification. Keep all paths inside the configured workspace. Inspect, act, observe, recover, validate, then finish. Never claim completion without observable evidence."""
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
                    conversation += "\n\nVERIFICATION FAILED: perform another tool action and verify the requested result."
                    actions[-1]["verification"] = evidence
                    continue
                return {"status": "completed", "execution_mode": "agentic", "summary": str(decision.get("summary", "Task completed.")), "steps": actions, "execution_evidence": evidence, "tool_records": tool_records}
            if action != "tool":
                raise AgentExecutionError("Invalid agent action.")
            tool = str(decision.get("tool", ""))
            args = decision.get("args", {})
            if tool not in self._TOOLS and tool not in self._TERMINAL_ALIASES:
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
            conversation += f"\n\nOBSERVATION step {step}: tool={tool}\n{serialized}\n\nContinue or verify before done."
        raise AgentExecutionError(f"Agent exceeded maximum execution steps ({self.max_steps}).")
