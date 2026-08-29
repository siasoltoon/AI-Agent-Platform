"""Production agentic execution loop with bounded tools and evidence-based completion."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.services.ollama_service import OllamaService
from tool_system.file_tools import (
    CopyFileTool, DeleteFileTool, DirectoryExistsTool, FileExistsTool, FileHashTool,
    ListDirectoryTool, MakeDirectoryTool, MoveFileTool, ReadFileTool, SearchFilesTool, WriteFileTool,
)
from tool_system.terminal_tools import TerminalTool


class AgentExecutionError(RuntimeError):
    """Raised when the agent cannot produce or execute a valid action."""


class AgentExecutor:
    """Execute tasks through a bounded plan/act/observe/verify loop."""

    _WORKSPACE_TOOLS = {
        "read_file", "write_file", "file_exists", "directory_exists", "list_directory",
        "make_directory", "search_files", "copy_file", "move_file", "delete_file", "file_hash",
    }
    _TERMINAL_ALIASES = {
        "type", "cat", "dir", "ls", "pwd", "where", "findstr", "fc", "tree", "more", "echo",
        "mkdir", "mktemp", "whoami", "hostname", "ver", "date", "time", "python", "py", "pytest",
        "pip", "pip3", "git", "uvicorn", "ruff", "black", "mypy", "node", "npm", "npm.cmd", "npx",
        "vite", "yarn", "pnpm", "dotnet", "java", "javac", "go", "cargo", "rustc", "pytest.exe",
        "python.exe", "node.exe", "npm.exe", "git.exe",
    }
    _TOOLS = _WORKSPACE_TOOLS | {"terminal"}
    _MUTATING_TOOLS = {"write_file", "make_directory", "copy_file", "move_file", "delete_file"}

    def __init__(self, ollama: OllamaService, workspace_root: str | None = None, max_steps: int = 32, max_output_chars: int = 12000) -> None:
        self.ollama = ollama
        self.workspace = Path(workspace_root or Path.cwd()).resolve()
        self.max_steps = max(1, min(int(max_steps), 64))
        self.max_output_chars = max(256, int(max_output_chars))
        self.read_file, self.write_file = ReadFileTool(), WriteFileTool()
        self.file_exists, self.directory_exists = FileExistsTool(), DirectoryExistsTool()
        self.list_directory, self.make_directory = ListDirectoryTool(), MakeDirectoryTool()
        self.search_files = SearchFilesTool()
        self.copy_file, self.move_file = CopyFileTool(), MoveFileTool()
        self.delete_file, self.file_hash = DeleteFileTool(), FileHashTool()
        self.terminal = TerminalTool()

    def _safe_path(self, path: str) -> Path:
        value = str(path).strip()
        if not value:
            raise AgentExecutionError("Path cannot be empty.")
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        candidate = candidate.resolve()
        if candidate != self.workspace and self.workspace not in candidate.parents:
            raise AgentExecutionError("Path escapes the configured workspace.")
        return candidate

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        text = str(text or "").strip()
        for candidate in [text, *re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)]:
            try:
                value = json.loads(candidate)
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                pass
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
        action = str(decision.get("action", "")).strip().lower()
        tool = str(decision.get("tool", "")).strip().lower()
        if action in cls._TOOLS:
            return {**decision, "action": "tool", "tool": tool or action}
        if action in cls._TERMINAL_ALIASES:
            return {**decision, "action": "tool", "tool": action}
        if tool in cls._TOOLS or tool in cls._TERMINAL_ALIASES:
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
            return f"echo {self._arg(args, 'text', 'message', 'content', default='')}".strip()
        command = str(self._arg(args, "command", "cmd", default=name)).strip()
        return command if command.split()[0].lower() == name.lower() else f"{name} {command}".strip()

    def _relative(self, path: Path) -> str:
        return "." if path == self.workspace else str(path.relative_to(self.workspace))

    def _tool(self, name: str, args: dict[str, Any]) -> Any:
        if name == "read_file":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath"))
            return {"ok": True, "path": self._relative(path), "content": self.read_file.execute(str(path))}
        if name == "write_file":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath"))
            content = str(self._arg(args, "content", "text", "body"))
            return {**self.write_file.execute(str(path), content), "path": self._relative(path)}
        if name == "file_exists":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath"))
            return {**self.file_exists.execute(str(path)), "path": self._relative(path), "ok": True}
        if name == "directory_exists":
            path = self._safe_path(self._arg(args, "path", "directory", default="."))
            return {**self.directory_exists.execute(str(path)), "path": self._relative(path), "ok": True}
        if name == "list_directory":
            path = self._safe_path(self._arg(args, "path", "directory", default="."))
            result = self.list_directory.execute(str(path))
            result["path"] = self._relative(path)
            return {"ok": True, **result}
        if name == "make_directory":
            path = self._safe_path(self._arg(args, "path", "directory"))
            result = self.make_directory.execute(str(path)); result["path"] = self._relative(path); return result
        if name == "search_files":
            path = self._safe_path(self._arg(args, "path", "directory", default="."))
            result = self.search_files.execute(str(path), str(self._arg(args, "pattern", default="*")))
            result["path"] = self._relative(path)
            result["matches"] = [self._relative(Path(p).resolve()) for p in result.get("matches", [])]
            return {"ok": True, **result}
        if name in {"copy_file", "move_file"}:
            source = self._safe_path(self._arg(args, "source", "src", "path"))
            destination = self._safe_path(self._arg(args, "destination", "dest", "target", "path2"))
            result = (self.copy_file if name == "copy_file" else self.move_file).execute(str(source), str(destination))
            result["source"], result["destination"] = self._relative(source), self._relative(destination); return result
        if name == "delete_file":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath"))
            result = self.delete_file.execute(str(path)); result["path"] = self._relative(path); return result
        if name == "file_hash":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath"))
            result = self.file_hash.execute(str(path), str(args.get("algorithm", "sha256"))); result["path"] = self._relative(path); return result
        command = str(self._arg(args, "command", "cmd", default="")).strip() if name == "terminal" else self._alias_command(name, args)
        if not command:
            raise AgentExecutionError("Terminal command cannot be empty.")
        timeout = int(args.get("timeout", 120))
        if timeout < 1 or timeout > 600:
            raise AgentExecutionError("Terminal timeout must be between 1 and 600 seconds.")
        return {**self.terminal.execute(command, timeout=timeout), "command": command}

    def _verify_evidence(self, task: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        successful = [r for r in records if r.get("ok") is True]
        failed = [r for r in records if r.get("ok") is not True]
        checks: list[dict[str, Any]] = []
        writes = [r for r in successful if r.get("tool") == "write_file"]
        reads = [r for r in successful if r.get("tool") == "read_file"]
        for record in writes:
            result = record.get("result", {}); rel = result.get("path"); expected = result.get("content")
            if not rel: continue
            path = self._safe_path(rel); exists = path.is_file()
            checks.append({"type": "file_exists", "path": rel, "passed": exists})
            if exists and isinstance(expected, str):
                checks.append({"type": "file_content_matches_write", "path": rel, "passed": path.read_text(encoding="utf-8") == expected})
        for record in reads:
            rel = record.get("result", {}).get("path")
            if rel: checks.append({"type": "read_verified_exists", "path": rel, "passed": self._safe_path(rel).is_file()})
        for record in successful:
            tool, result = record.get("tool"), record.get("result", {})
            if tool == "make_directory":
                rel = result.get("path")
                if rel: checks.append({"type": "directory_exists", "path": rel, "passed": self._safe_path(rel).is_dir()})
            elif tool == "copy_file":
                rel = result.get("destination")
                if rel: checks.append({"type": "copied_file_exists", "path": rel, "passed": self._safe_path(rel).is_file()})
            elif tool == "move_file":
                src, dst = result.get("source"), result.get("destination")
                if src and dst: checks.extend([
                    {"type": "move_destination_exists", "path": dst, "passed": self._safe_path(dst).exists()},
                    {"type": "move_source_absent", "path": src, "passed": not self._safe_path(src).exists()},
                ])
            elif tool == "delete_file":
                rel = result.get("path")
                if rel: checks.append({"type": "file_absent_after_delete", "path": rel, "passed": not self._safe_path(rel).exists()})
        for record in successful:
            if record.get("tool") in {"terminal", *self._TERMINAL_ALIASES}:
                result = record.get("result", {})
                checks.append({"type": "terminal_success", "command": result.get("command"), "passed": result.get("code") == 0})

        lower = task.lower()
        mutating = bool(successful and any(r.get("tool") in self._MUTATING_TOOLS for r in successful))
        verification_requested = any(word in lower for word in ("verify", "check", "confirm", "ensure", "exactly", "read"))
        required = [c for c in checks if c["type"] not in {"terminal_success"}]
        verified = bool(successful) and not failed and (all(c["passed"] for c in required) if required else True)
        if writes and verification_requested and not reads:
            verified = False
        if mutating and not required:
            verified = False
        return {"verified": verified, "checks": checks, "successful_tool_actions": len(successful), "failed_tool_actions": len(failed)}

    def execute(self, task: str) -> dict[str, Any]:
        if not task or not task.strip(): raise AgentExecutionError("Task cannot be empty.")
        system = """You are the production autonomous coding agent.
Return exactly one JSON object per turn:
{"action":"tool","tool":"TOOL_NAME","args":{...}} or {"action":"done","summary":"..."}

Workspace tools: read_file, write_file, file_exists, directory_exists, list_directory, make_directory, search_files, copy_file, move_file, delete_file, file_hash.
Execution tool: terminal. Terminal aliases include type, cat, dir, ls, pwd, where, findstr, fc, tree, more, echo, mkdir, python, py, pytest, pip, git, uvicorn, ruff, black, mypy, node, npm, npx, vite, yarn, pnpm, dotnet, java, javac, go, cargo, rustc.

Rules: stay inside workspace; inspect before risky changes; prefer dedicated tools; after every mutation perform observable verification; for requested content read it and verify exact equality; never claim completion without evidence; recover from transient failures when possible; return done only when evidence supports success."""
        conversation = f"{system}\n\nTASK:\n{task.strip()}\n\nWORKSPACE:\n{self.workspace}"
        actions: list[dict[str, Any]] = []; records: list[dict[str, Any]] = []
        for step in range(1, self.max_steps + 1):
            response = self.ollama.generate(conversation, timeout=self.ollama.timeout)
            decision = self._normalize_decision(self._extract_json(response.get("response", "")))
            actions.append({"step": step, "decision": decision})
            if decision.get("action") == "done":
                evidence = self._verify_evidence(task, records); actions[-1]["verification"] = evidence
                if records and evidence["verified"]:
                    return {"status":"completed","execution_mode":"agentic","summary":str(decision.get("summary","Task completed.")),"steps":actions,"execution_evidence":evidence,"tool_records":records}
                conversation += "\n\nVERIFICATION FAILED. Continue with observable verification; do not claim success yet."
                continue
            if decision.get("action") != "tool": raise AgentExecutionError("Invalid agent action.")
            tool = str(decision.get("tool", "")).strip().lower(); args = decision.get("args", {})
            if tool not in self._TOOLS and tool not in self._TERMINAL_ALIASES: raise AgentExecutionError(f"Unknown tool: {tool}")
            if not isinstance(args, dict): raise AgentExecutionError("Tool args must be an object.")
            try: result = self._tool(tool, args); record = {"step":step,"tool":tool,"ok":True,"result":result}
            except Exception as exc: record = {"step":step,"tool":tool,"ok":False,"error_type":type(exc).__name__,"error":str(exc)}; result={"ok":False,"error_type":type(exc).__name__,"error":str(exc)}
            records.append(record)
            serialized = json.dumps(result, ensure_ascii=False, default=str)
            if len(serialized) > self.max_output_chars: serialized = serialized[:self.max_output_chars] + "...<truncated>"
            conversation += f"\n\nOBSERVATION step {step}: tool={tool}\n{serialized}\n\nContinue, recover, or verify before done."
        raise AgentExecutionError(f"Agent exceeded maximum execution steps ({self.max_steps}).")
