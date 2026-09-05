"""Controlled terminal tool for agentic project execution."""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any

from agent_core.security_boundary import WorkspaceBoundary

from .base_tool import BaseTool
from .process_runner import IsolatedProcessRunner, ProcessLimits


class TerminalTool(BaseTool):
    name = "terminal"

    _ALLOWED = {
        "python", "py", "pytest", "pip", "pip3", "git", "uvicorn", "ruff", "black", "mypy",
        "node", "npm", "npm.cmd", "npx", "vite", "yarn", "pnpm",
        "dir", "ls", "pwd", "type", "cat", "more", "where", "findstr", "fc", "tree", "echo",
        "mkdir", "mktemp", "whoami", "hostname", "ver", "date", "time",
        "dotnet", "java", "javac", "go", "cargo", "rustc",
        "pytest.exe", "python.exe", "node.exe", "npm.exe", "git.exe",
    }
    _BLOCKED_COMMANDS = {
        "del", "erase", "format", "shutdown", "restart", "taskkill", "diskpart", "reg",
        "powershell", "pwsh", "cmd", "rmdir", "rd", "rm", "sudo", "chmod", "chown",
    }
    _SHELL_OPERATORS = frozenset(";&|><`")
    _SAFE_ENV_KEYS = frozenset({
        "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR",
        "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "LANG", "LC_ALL", "LC_CTYPE",
        "VIRTUAL_ENV",
    })
    MAX_OUTPUT_CHARS = 12_000

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace = Path(workspace_root or Path.cwd()).resolve()
        self._boundary = WorkspaceBoundary(self.workspace)
        self._runner = IsolatedProcessRunner(environment=self._safe_environment())

    @staticmethod
    def _truncate(value: str) -> str:
        if len(value) <= TerminalTool.MAX_OUTPUT_CHARS:
            return value
        omitted = len(value) - TerminalTool.MAX_OUTPUT_CHARS
        return value[: TerminalTool.MAX_OUTPUT_CHARS] + f"\n...<truncated {omitted} chars>"

    @classmethod
    def _contains_blocked_shell_syntax(cls, command: str) -> bool:
        quote: str | None = None
        escaped = False
        for char in command:
            if escaped:
                escaped = False
                continue
            if char == "\\" and quote != "'":
                escaped = True
                continue
            if quote:
                if char == quote:
                    quote = None
                continue
            if char in {"'", '"'}:
                quote = char
                continue
            if char in cls._SHELL_OPERATORS:
                return True
        return quote is not None

    @classmethod
    def _contains_blocked_command(cls, command: str) -> bool:
        try:
            tokens = __import__("shlex").split(command, posix=True)
        except ValueError:
            return True
        return any(token.lower() in cls._BLOCKED_COMMANDS for token in tokens)

    @classmethod
    def _safe_environment(cls) -> dict[str, str]:
        """Pass only non-secret process configuration needed by developer toolchains."""
        return {key: value for key, value in __import__("os").environ.items() if key.upper() in cls._SAFE_ENV_KEYS}

    def _safe_path(self, path: str | Path) -> Path:
        return self._boundary.assert_safe(path)

    def execute(self, command: str, timeout: int = 120) -> dict[str, Any]:
        command = str(command).strip()
        if not command:
            raise ValueError("Terminal command cannot be empty.")
        if timeout < 1 or timeout > 600:
            raise ValueError("Terminal timeout must be between 1 and 600 seconds.")

        try:
            tokens = shlex.split(command, posix=True)
        except ValueError as exc:
            raise PermissionError("Terminal command contains invalid shell syntax.") from exc
        executable = tokens[0].strip('"\'').lower() if tokens else ""
        if executable not in self._ALLOWED:
            raise PermissionError(f"Terminal command is not allowed: {executable}")
        if self._contains_blocked_shell_syntax(command) or self._contains_blocked_command(command):
            raise PermissionError("Terminal command contains a blocked operation.")

        if executable == "type":
            target = tokens[1] if len(tokens) > 1 else ""
            if not target or target.upper() == "NUL":
                return {"stdout": "", "stderr": "", "code": 0, "timed_out": False}
            path = self._safe_path(target)
            try:
                if path.is_file():
                    return {"stdout": self._truncate(path.read_text(encoding="utf-8")), "stderr": "", "code": 0, "timed_out": False}
            except OSError as exc:
                return {"stdout": "", "stderr": str(exc), "code": 1, "timed_out": False}

        if executable == "mkdir":
            targets = [part for part in tokens[1:] if part not in {"-p", "--parents"}]
            if not targets:
                raise ValueError("mkdir requires a directory path.")
            for target in targets:
                self._safe_path(target).mkdir(parents=True, exist_ok=True)
            return {"stdout": "", "stderr": "", "code": 0, "timed_out": False}

        result_stdout, result_stderr, returncode, timed_out = self._runner.run(
            tokens,
            cwd=str(self.workspace),
            limits=ProcessLimits(timeout_seconds=timeout, max_output_chars=self.MAX_OUTPUT_CHARS),
        )
        return {
            "stdout": self._truncate(result_stdout),
            "stderr": self._truncate(result_stderr),
            "code": returncode,
            "timed_out": timed_out,
            **({"timeout_seconds": timeout} if timed_out else {}),
            "process_isolation": "new_process_group",
            "environment_policy": "allowlist",
            "shell": False,
        }
