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

        # ``type`` is a Windows file-reading alias. Hosted CI is Linux, where
        # shell ``type`` has different semantics, so emulate the bounded
        # contract directly on every platform.
        if executable == "type":
            parts = shlex.split(command, posix=True)
            target = parts[1] if len(parts) > 1 else ""
            if not target or target.upper() == "NUL":
                return {"stdout": "", "stderr": "", "code": 0, "timed_out": False}
            path = Path(target)
            try:
                if path.is_file():
                    return {"stdout": path.read_text(encoding="utf-8"), "stderr": "", "code": 0, "timed_out": False}
            except OSError as exc:
                return {"stdout": "", "stderr": str(exc), "code": 1, "timed_out": False}

        # ``mkdir`` is exposed as a terminal alias for compatibility, but
        # directory creation is an idempotent workspace mutation. Implement
        # it directly so an already-existing directory is a successful
        # no-op instead of a shell error that can derail an otherwise valid
        # agent task.
        if executable == "mkdir":
            parts = shlex.split(command, posix=True)
            targets = [part for part in parts[1:] if part not in {"-p", "--parents"}]
            if not targets:
                raise ValueError("mkdir requires a directory path.")
            for target in targets:
                Path(target).mkdir(parents=True, exist_ok=True)
            return {"stdout": "", "stderr": "", "code": 0, "timed_out": False}

        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"stdout": result.stdout, "stderr": result.stderr, "code": result.returncode, "timed_out": False}
