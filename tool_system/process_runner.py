"""Process-level controls for terminal tool execution.

This module intentionally provides process isolation and bounded execution, not an
OS sandbox. Filesystem confinement remains the responsibility of WorkspaceBoundary.
"""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ProcessLimits:
    """Portable process limits enforced by the runner."""

    timeout_seconds: int
    max_output_chars: int


class IsolatedProcessRunner:
    """Run one process in its own process group and terminate the group on timeout."""

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
        )
        try:
            stdout, stderr = process.communicate(timeout=limits.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            self._kill_process_tree(process)
            stdout, stderr = process.communicate()
            timeout_message = f"Command timed out after {limits.timeout_seconds} seconds."
            if not stderr:
                stderr = timeout_message
            elif timeout_message not in stderr:
                stderr = f"{stderr}\n{timeout_message}"
            return stdout or "", stderr or "", 124, True
        return stdout, stderr, process.returncode, False
