"""Controlled terminal tool for agentic project execution."""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any

from agent_core.execution_fence import ExecutionFence
from agent_core.network_policy import NetworkPolicy
from agent_core.security_boundary import WorkspaceBoundary
from .base_tool import BaseTool
from .process_runner import IsolatedProcessRunner, ProcessLimits


class TerminalTool(BaseTool):
    name = "terminal"
    _ALLOWED = {"python", "py", "pytest", "pip", "pip3", "git", "uvicorn", "ruff", "black", "mypy", "node", "npm", "npm.cmd", "npx", "vite", "yarn", "pnpm", "dir", "ls", "pwd", "type", "cat", "more", "where", "findstr", "fc", "tree", "echo", "mkdir", "mktemp", "whoami", "hostname", "ver", "date", "time", "dotnet", "java", "javac", "go", "cargo", "rustc", "pytest.exe", "python.exe", "node.exe", "npm.exe", "git.exe"}
    _BLOCKED_COMMANDS = {"del", "erase", "format", "shutdown", "restart", "taskkill", "diskpart", "reg", "powershell", "pwsh", "cmd", "rmdir", "rd", "rm", "sudo", "chmod", "chown"}
    _SHELL_OPERATORS = frozenset(";&|><`")
    _SAFE_ENV_KEYS = frozenset({"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "LANG", "LC_ALL", "LC_CTYPE", "VIRTUAL_ENV"})
    MAX_OUTPUT_CHARS = 12_000

    def __init__(self, workspace_root: str | Path | None = None, network_policy: NetworkPolicy | None = None, execution_fence: ExecutionFence | None = None) -> None:
        self.workspace = Path(workspace_root or Path.cwd()).resolve()
        self._boundary = WorkspaceBoundary(self.workspace)
        self.network_policy = network_policy or NetworkPolicy()
        self.execution_fence = execution_fence
        self._runner = IsolatedProcessRunner(environment=self._safe_environment(), network_sandbox=self._network_sandbox())

    def _network_sandbox(self):
        from agent_core.network_sandbox import NetworkSandbox
        if self.network_policy.mode == "native": return NetworkSandbox("native")
        return NetworkSandbox("command-policy")

    @staticmethod
    def _truncate(value: str) -> str:
        if len(value) <= TerminalTool.MAX_OUTPUT_CHARS: return value
        omitted = len(value) - TerminalTool.MAX_OUTPUT_CHARS
        return value[: TerminalTool.MAX_OUTPUT_CHARS] + f"\n...<truncated {omitted} chars>"

    @classmethod
    def _contains_blocked_shell_syntax(cls, command: str) -> bool:
        quote = None; escaped = False
        for char in command:
            if escaped: escaped = False; continue
            if char == "\\" and quote != "'": escaped = True; continue
            if quote:
                if char == quote: quote = None
                continue
            if char in {"'", '"'}: quote = char; continue
            if char in cls._SHELL_OPERATORS: return True
        return quote is not None

    @classmethod
    def _contains_blocked_command(cls, command: str) -> bool:
        try: tokens = shlex.split(command, posix=True)
        except ValueError: return True
        return any(token.lower() in cls._BLOCKED_COMMANDS for token in tokens)

    @classmethod
    def _safe_environment(cls) -> dict[str, str]:
        return {key: value for key, value in os.environ.items() if key.upper() in cls._SAFE_ENV_KEYS}

    def _safe_path(self, path: str | Path) -> Path: return self._boundary.assert_safe(path)

    def _fence_begin(self, command: str, executable: str) -> str | None:
        if self.execution_fence is None: return None
        key, record = self.execution_fence.begin_side_effect(executable, {"command": command, "workspace": str(self.workspace)})
        if record.get("state") == "committed": return key
        return key

    def _fence_commit(self, key: str | None, result: dict[str, Any]) -> dict[str, Any]:
        if self.execution_fence is None or key is None: return result
        return self.execution_fence.commit_side_effect(key, result)

    def execute(self, command: str, timeout: int = 120) -> dict[str, Any]:
        command = str(command).strip()
        if not command: raise ValueError("Terminal command cannot be empty.")
        if timeout < 1 or timeout > 600: raise ValueError("Terminal timeout must be between 1 and 600 seconds.")
        try: tokens = shlex.split(command, posix=True)
        except ValueError as exc: raise PermissionError("Terminal command contains invalid shell syntax.") from exc
        executable = tokens[0].strip('"\'').lower() if tokens else ""
        if executable not in self._ALLOWED: raise PermissionError(f"Terminal command is not allowed: {executable}")
        if self._contains_blocked_shell_syntax(command) or self._contains_blocked_command(command): raise PermissionError("Terminal command contains a blocked operation.")
        self.network_policy.check_command(executable, command)
        network_evidence = self.network_policy.evidence(executable, allowed=True)
        key = self._fence_begin(command, executable)
        try:
            if self.execution_fence is not None: self.execution_fence.assert_current()
            if executable == "type":
                target = tokens[1] if len(tokens) > 1 else ""
                if not target or target.upper() == "NUL": result = {"stdout": "", "stderr": "", "code": 0, "timed_out": False, "network_policy": network_evidence, "network_isolation": self._runner.network_isolation()}; return self._fence_commit(key, result)
                path = self._safe_path(target)
                try:
                    if path.is_file(): result = {"stdout": self._truncate(path.read_text(encoding="utf-8")), "stderr": "", "code": 0, "timed_out": False, "network_policy": network_evidence, "network_isolation": self._runner.network_isolation()}; return self._fence_commit(key, result)
                except OSError as exc: result = {"stdout": "", "stderr": str(exc), "code": 1, "timed_out": False, "network_policy": network_evidence, "network_isolation": self._runner.network_isolation()}; return self._fence_commit(key, result)
            if executable == "mkdir":
                targets = [part for part in tokens[1:] if part not in {"-p", "--parents"}]
                if not targets: raise ValueError("mkdir requires a directory path.")
                for target in targets: self._safe_path(target).mkdir(parents=True, exist_ok=True)
                return self._fence_commit(key, {"stdout": "", "stderr": "", "code": 0, "timed_out": False, "network_policy": network_evidence, "network_isolation": self._runner.network_isolation()})
            result_stdout, result_stderr, returncode, timed_out = self._runner.run(tokens, cwd=str(self.workspace), limits=ProcessLimits(timeout_seconds=timeout, max_output_chars=self.MAX_OUTPUT_CHARS))
            if self.execution_fence is not None: self.execution_fence.assert_current()
            result = {"stdout": self._truncate(result_stdout), "stderr": self._truncate(result_stderr), "code": returncode, "timed_out": timed_out, **({"timeout_seconds": timeout} if timed_out else {}), "process_isolation": "new_process_group", "native_os_isolation": self._runner.isolation_mode(), "environment_policy": "allowlist", "network_policy": network_evidence, "network_isolation": self._runner.network_isolation(), "shell": False}
            return self._fence_commit(key, result)
        except Exception as exc:
            if self.execution_fence is not None and key is not None: self.execution_fence.mark_ambiguous(key, str(exc))
            raise
