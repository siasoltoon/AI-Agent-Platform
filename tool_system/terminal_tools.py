"""Controlled terminal tool for agentic project execution."""

from __future__ import annotations

import re
import subprocess
from typing import Any

from .base_tool import BaseTool


class TerminalTool(BaseTool):
    name = "terminal"

    # Commands commonly required by this Python project. The agent is not given
    # an unrestricted shell because model-generated shell commands are untrusted.
    _ALLOWED = {
        "python",
        "py",
        "pytest",
        "pip",
        "git",
        "uvicorn",
        "ruff",
        "black",
        "mypy",
    }
    _BLOCKED = re.compile(
        r"(?:\b(?:del|erase|format|shutdown|restart|taskkill|diskpart|reg|powershell|pwsh|cmd)\b|"
        r"[;&|><`]|(?:\b(?:rm|sudo|chmod|chown)\b))",
        re.IGNORECASE,
    )

    def execute(self, command: str, timeout: int = 120) -> dict[str, Any]:
        command = str(command).strip()
        if not command:
            raise ValueError("Terminal command cannot be empty.")
        if timeout < 1 or timeout > 600:
            raise ValueError("Terminal timeout must be between 1 and 600 seconds.")
        if self._BLOCKED.search(command):
            raise PermissionError("Terminal command contains a blocked operation.")

        executable = command.split()[0].strip('"\'').lower()
        if executable.endswith(".exe"):
            executable = executable[:-4]
        if executable not in self._ALLOWED:
            raise PermissionError(f"Terminal command is not allowed: {executable}")

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
