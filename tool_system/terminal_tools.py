"""Controlled terminal tool for agentic project execution."""

from __future__ import annotations

import re
import subprocess
from typing import Any

from .base_tool import BaseTool


class TerminalTool(BaseTool):
    name = "terminal"

    # Broad but intentionally bounded command coverage. Mutation of workspace
    # files should prefer the dedicated file tools; these commands cover
    # inspection, development, testing, package management and version control.
    _ALLOWED = {
        "python", "py", "pytest", "pip", "pip3", "git", "uvicorn", "ruff", "black", "mypy",
        "node", "npm", "npm.cmd", "npx", "vite", "yarn", "pnpm",
        "dir", "ls", "pwd", "type", "cat", "more", "where", "findstr", "fc", "tree", "echo",
        "mkdir", "mktemp", "whoami", "hostname", "ver", "date", "time",
        "dotnet", "java", "javac", "go", "cargo", "rustc",
        "pytest.exe", "python.exe", "node.exe", "npm.exe", "git.exe",
    }
    _ALIASES = {
        "npm.cmd": "npm",
        "pytest.exe": "pytest",
        "python.exe": "python",
        "node.exe": "node",
        "npm.exe": "npm",
        "git.exe": "git",
    }
    _BLOCKED = re.compile(
        r"(?:\b(?:del|erase|format|shutdown|restart|taskkill|diskpart|reg|powershell|pwsh|cmd|rmdir|rd)\b|"
        r"[;&|><`]|(?:\b(?:rm|sudo|chmod|chown)\b))",
        re.IGNORECASE,
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

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "code": result.returncode,
            "timed_out": False,
        }
