"""Process-level controls for terminal tool execution.

This module provides process-group isolation and bounded execution. It is still not
an OS sandbox; callers must provide a workspace boundary and treat the runner as a
resource-control layer.
"""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ProcessLimits:
    """Hard execution ceilings where the host operating system supports them."""

    timeout_seconds: int
    max_output_chars: int
    max_cpu_seconds: int = 120
    max_memory_bytes: int = 2 * 1024 * 1024 * 1024
    max_processes: int = 64

    def __post_init__(self) -> None:
        if self.timeout_seconds < 1 or self.max_output_chars < 1:
            raise ValueError("Process timeout and output limits must be positive")
        if self.max_cpu_seconds < 1 or self.max_memory_bytes < 1 or self.max_processes < 1:
            raise ValueError("Process resource limits must be positive")


class IsolatedProcessRunner:
    """Run one process in its own process group with bounded resources."""

    def __init__(self, *, environment: Mapping[str, str]) -> None:
        self.environment = dict(environment)

    @staticmethod
    def _creationflags() -> int:
        if os.name != "nt":
            return 0
        return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    @staticmethod
    def _start_new_session() -> bool:
        return os.name != "nt"

    @staticmethod
    def _resource_preexec(limits: ProcessLimits):
        if os.name == "nt":
            return None
        try:
            import resource
        except ImportError:
            return None

        def apply_limits() -> None:
            resource.setrlimit(resource.RLIMIT_CPU, (limits.max_cpu_seconds, limits.max_cpu_seconds))
            resource.setrlimit(resource.RLIMIT_AS, (limits.max_memory_bytes, limits.max_memory_bytes))
            if hasattr(resource, "RLIMIT_NPROC"):
                resource.setrlimit(resource.RLIMIT_NPROC, (limits.max_processes, limits.max_processes))

        return apply_limits

    @staticmethod
    def _kill_process_tree(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
                return
            except (OSError, ProcessLookupError):
                pass
        try:
            process.kill()
        except OSError:
            pass

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: str,
        limits: ProcessLimits,
    ) -> tuple[str, str, int, bool]:
        process = subprocess.Popen(
            list(args),
            shell=False,
            cwd=cwd,
            env=self.environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=self._creationflags(),
            start_new_session=self._start_new_session(),
            preexec_fn=self._resource_preexec(limits),
        )
        try:
            stdout, stderr = process.communicate(timeout=limits.timeout_seconds)
        except subprocess.TimeoutExpired:
            self._kill_process_tree(process)
            stdout, stderr = process.communicate()
            timeout_message = f"Command timed out after {limits.timeout_seconds} seconds."
            if not stderr:
                stderr = timeout_message
            elif timeout_message not in stderr:
                stderr = f"{stderr}\n{timeout_message}"
            return stdout or "", stderr or "", 124, True
        return stdout, stderr, process.returncode, False
