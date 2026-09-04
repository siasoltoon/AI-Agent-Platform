"""Production agentic execution loop with bounded tools and evidence-based completion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.action_parser import ActionParseError, ActionParser
from agent_core.mission_policy import MissionPolicy
from backend.services.ollama_service import OllamaService
from tool_system.file_tools import (
    CopyFileTool,
    DeleteFileTool,
    DirectoryExistsTool,
    FileExistsTool,
    FileHashTool,
    ListDirectoryTool,
    MakeDirectoryTool,
    MoveFileTool,
    ReadFileTool,
    SearchFilesTool,
    WriteFileTool,
)
from tool_system.terminal_tools import TerminalTool


class AgentExecutionError(RuntimeError):
    """Raised when the agent cannot produce or execute a valid action."""

    def __init__(self, message: str, *, partial_result: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.partial_result = partial_result


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
        self.read_file = ReadFileTool(workspace_root=self.workspace)
        self.write_file = WriteFileTool(workspace_root=self.workspace)
        self.file_exists = FileExistsTool(workspace_root=self.workspace)
        self.directory_exists = DirectoryExistsTool(workspace_root=self.workspace)
        self.list_directory = ListDirectoryTool(workspace_root=self.workspace)
        self.make_directory = MakeDirectoryTool(workspace_root=self.workspace)
        self.search_files = SearchFilesTool(workspace_root=self.workspace)
        self.copy_file = CopyFileTool(workspace_root=self.workspace)
        self.move_file = MoveFileTool(workspace_root=self.workspace)
        self.delete_file = DeleteFileTool(workspace_root=self.workspace)
        self.file_hash = FileHashTool(workspace_root=self.workspace)
        self.terminal = TerminalTool(workspace_root=self.workspace)

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

    @classmethod
    def _normalize_decision(cls, decision: dict[str, Any]) -> dict[str, Any]:
        return ActionParser.normalize(decision, cls._TOOLS, cls._TERMINAL_ALIASES)

    @staticmethod
    def _arg(args: dict[str, Any], *names: str, default: Any = "") -> Any:
        for name in names:
            value = args.get(name)
            if value is not None and str(value).strip():
                return value
        return default

    def _relative(self, path: Path) -> str:
        if path == self.workspace:
            return "."
        return path.relative_to(self.workspace).as_posix()

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
        if not command:
            return name
        return command if command.split()[0].lower() == name.lower() else f"{name} {command}".strip()

    def _tool(self, name: str, args: dict[str, Any]) -> Any:
        if name == "read_file":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath"))
            return {"ok": True, "path": self._relative(path), "content": self.read_file.execute(str(path))}
        if name == "write_file":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath"))
            content = str(self._arg(args, "content", "text", "body"))
            result = self.write_file.execute(str(path), content)
            return {**result, "path": self._relative(path), "content": content}
        if name == "file_exists":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath"))
            return {**self.file_exists.execute(str(path)), "path": self._relative(path), "ok": True}
        if name == "directory_exists":
            path = self._safe_path(self._arg(args, "path", "directory", default="."))
            return {**self.directory_exists.execute(str(path)), "path": self._relative(path), "ok": True}
        if name == "list_directory":
            path = self._safe_path(self._arg(args, "path", "directory", default="."))
            result = self.list_directory.execute(str(path))
            return {"ok": True, **result, "path": self._relative(path)}
        if name == "make_directory":
            path = self._safe_path(self._arg(args, "path", "directory"))
            result = self.make_directory.execute(str(path))
            result["path"] = self._relative(path)
            return result
        if name == "search_files":
            path = self._safe_path(self._arg(args, "path", "directory", default="."))
            result = self.search_files.execute(str(path), str(self._arg(args, "pattern", default="*")))
            result["path"] = self._relative(path)
            result["matches"] = [self._relative(Path(p).resolve()) for p in result.get("matches", [])]
            return {"ok": True, **result}
        if name in {"copy_file", "move_file"}:
            source = self._safe_path(self._arg(args, "source", "src", "path"))
            destination = self._safe_path(self._arg(args, "destination", "dest", "target", "path2"))
            tool = self.copy_file if name == "copy_file" else self.move_file
            result = tool.execute(str(source), str(destination))
            result["source"] = self._relative(source)
            result["destination"] = self._relative(destination)
            return result
        if name == "delete_file":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath"))
            result = self.delete_file.execute(str(path))
            result["path"] = self._relative(path)
            return result
        if name == "file_hash":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath"))
            result = self.file_hash.execute(str(path), str(args.get("algorithm", "sha256")))
            result["path"] = self._relative(path)
            return result

        command = str(self._arg(args, "command", "cmd", default="")).strip() if name == "terminal" else self._alias_command(name, args)
        if not command:
            raise AgentExecutionError("Terminal command cannot be empty.")
        timeout = int(args.get("timeout", 120))
        if timeout < 1 or timeout > 600:
            raise AgentExecutionError("Terminal timeout must be between 1 and 600 seconds.")
        return {**self.terminal.execute(command, timeout=timeout), "command": command}

    @staticmethod
    def _verification_requested(task: str) -> bool:
        lower = task.lower()
        return any(word in lower for word in ("verify", "check", "confirm", "ensure", "exactly", "read"))

    def _verify_evidence(self, task: str, records: list[dict[str, Any]], policy: MissionPolicy | None = None) -> dict[str, Any]:
        policy = policy or MissionPolicy.from_task(task)
        successful = [record for record in records if record.get("ok") is True]
        failed = [record for record in records if record.get("ok") is not True]
        checks: list[dict[str, Any]] = []

        writes = [record for record in successful if record.get("tool") == "write_file"]
        reads = [record for record in successful if record.get("tool") == "read_file"]
        write_contents = {
            record.get("result", {}).get("path"): record.get("result", {}).get("content")
            for record in writes
            if record.get("result", {}).get("path")
        }

        for record in writes:
            result = record.get("result", {})
            rel = result.get("path")
            expected = result.get("content")
            if not rel:
                continue
            path = self._safe_path(rel)
            exists = path.is_file()
            checks.append({"type": "file_exists", "path": rel, "passed": exists})
            if exists and isinstance(expected, str):
                try:
                    actual = path.read_text(encoding="utf-8")
                    checks.append({"type": "file_content_matches_write", "path": rel, "expected_content": expected, "passed": actual == expected})
                except OSError as exc:
                    checks.append({"type": "file_content_readable", "path": rel, "passed": False, "error": str(exc)})

        for record in reads:
            result = record.get("result", {})
            rel = result.get("path")
            if not rel:
                continue
            path = self._safe_path(rel)
            checks.append({"type": "read_file_exists", "path": rel, "passed": path.is_file()})

        if policy.read_only and any(record.get("tool") in self._MUTATING_TOOLS and record.get("ok") is True for record in records):
            checks.append({"type": "read_only_policy", "passed": False})
        else:
            checks.append({"type": "read_only_policy", "passed": True})

        if self._verification_requested(task):
            checks.append({"type": "observation", "passed": bool(successful)})

        return {
            "verified": bool(successful) and not failed and all(check.get("passed") for check in checks),
            "checks": checks,
            "successful_tool_calls": len(successful),
            "failed_tool_calls": len(failed),
        }
