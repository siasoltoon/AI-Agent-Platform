"""Controlled terminal tool for agentic project execution."""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .base_tool import BaseTool


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
    _ALIASES = {
        "npm.cmd": "npm", "pytest.exe": "pytest", "python.exe": "python",
        "node.exe": "node", "npm.exe": "npm", "git.exe": "git",
    }
    _BLOCKED = re.compile(
        r"(?:\b(?:del|erase|format|shutdown|restart|taskkill|diskpart|reg|powershell|pwsh|cmd|rmdir|rd)\b|"
        r"[;&|><`]|(?:\b(?:rm|sudo|chmod|chown)\b))", re.IGNORECASE,
    )
    MAX_OUTPUT_CHARS = 12_000

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace = Path(workspace_root or Path.cwd()).resolve()

    @staticmethod
    def _truncate(value: str) -> str:
        if len(value) <= TerminalTool.MAX_OUTPUT_CHARS:
            return value
        omitted = len(value) - TerminalTool.MAX_OUTPUT_CHARS
        return value[: TerminalTool.MAX_OUTPUT_CHARS] + f"\n...<truncated {omitted} chars>"

    def execute(self, command: str, timeout: int = 120) -> dict[str, Any]:
        command = str(command).strip()
        if not command:
            raise ValueError("Terminal command cannot be empty.")
        if timeout < 1 or timeout > 600:
            raise ValueError("Terminal timeout must be between 1 and 600 seconds.")

        executable = command.split()[0].strip('"\'').lower()
        if executable not in self._ALLOWED:
            raise PermissionError(f"Terminal command is not allowed: {executable}")
        if self._BLOCKED.search(command):
            raise PermissionError("Terminal command contains a blocked operation.")

        if executable == "type":
            parts = shlex.split(command, posix=True)
            target = parts[1] if len(parts) > 1 else ""
            if not target or target.upper() == "NUL":
                return {"stdout": "", "stderr": "", "code": 0, "timed_out": False}
            path = Path(target)
            try:
                if path.is_file():
                    return {"stdout": self._truncate(path.read_text(encoding="utf-8")), "stderr": "", "code": 0, "timed_out": False}
            except OSError as exc:
                return {"stdout": "", "stderr": str(exc), "code": 1, "timed_out": False}

        if executable == "mkdir":
            parts = shlex.split(command, posix=True)
            targets = [part for part in parts[1:] if part not in {"-p", "--parents"}]
            if not targets:
                raise ValueError("mkdir requires a directory path.")
            for target in targets:
                path = Path(target)
                resolved = path.resolve() if path.is_absolute() else (self.workspace / path).resolve()
                if resolved != self.workspace and self.workspace not in resolved.parents:
                    raise PermissionError("Terminal path escapes the configured workspace.")
                resolved.mkdir(parents=True, exist_ok=True)
            return {"stdout": "", "stderr": "", "code": 0, "timed_out": False}

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            return {
                "stdout": self._truncate(stdout),
                "stderr": self._truncate(stderr or f"Command timed out after {timeout} seconds."),
                "code": 124,
                "timed_out": True,
                "timeout_seconds": timeout,
            }
        return {
            "stdout": self._truncate(result.stdout),
            "stderr": self._truncate(result.stderr),
            "code": result.returncode,
            "timed_out": False,
        }
