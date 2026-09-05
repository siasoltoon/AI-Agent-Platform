"""Host OS process containment for worker execution.

This module adds stronger process containment where the host OS provides a native
primitive. Windows uses Job Objects to keep child processes inside one managed job
and enforce memory/process-count ceilings. POSIX resource limits remain owned by
``tool_system.process_runner``. This is still not a complete filesystem or network
sandbox.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OSIsolationResult:
    """Describe the native containment that was successfully attached."""

    mode: str
    enforced: bool
    memory_limit_bytes: int
    process_limit: int

    def snapshot(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "enforced": self.enforced,
            "memory_limit_bytes": self.memory_limit_bytes,
            "process_limit": self.process_limit,
        }


class OSIsolationError(RuntimeError):
    """Raised when native process containment cannot be established."""


class WindowsJobIsolation:
    """Attach a worker process to a Windows Job Object with hard limits."""

    def __init__(self, *, memory_limit_bytes: int, process_limit: int) -> None:
        self.memory_limit_bytes = memory_limit_bytes
        self.process_limit = process_limit
        self._handle = None
        self._kernel32 = None

    def attach(self, process: Any) -> OSIsolationResult:
        if os.name != "nt":
            return OSIsolationResult(
                mode="posix-rlimits",
                enforced=False,
                memory_limit_bytes=self.memory_limit_bytes,
                process_limit=self.process_limit,
            )

        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32 = kernel32
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, wintypes.INT, wintypes.LPVOID, wintypes.DWORD]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
            )]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
        JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
        PROCESS_TERMINATE = 0x0001
        PROCESS_SET_QUOTA = 0x0100
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise OSIsolationError(f"CreateJobObjectW failed: {ctypes.get_last_error()}")

        self._handle = job
        limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | JOB_OBJECT_LIMIT_JOB_MEMORY
            | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        limits.BasicLimitInformation.ActiveProcessLimit = self.process_limit
        limits.JobMemoryLimit = self.memory_limit_bytes

        if not kernel32.SetInformationJobObject(
            job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            self.close()
            raise OSIsolationError(f"SetInformationJobObject failed: {ctypes.get_last_error()}")

        process_handle = kernel32.OpenProcess(PROCESS_TERMINATE | PROCESS_SET_QUOTA, False, int(process.pid))
        if not process_handle:
            self.close()
            raise OSIsolationError(f"OpenProcess failed: {ctypes.get_last_error()}")
        try:
            if not kernel32.AssignProcessToJobObject(job, process_handle):
                error = ctypes.get_last_error()
                self.close()
                raise OSIsolationError(f"AssignProcessToJobObject failed: {error}")
        finally:
            kernel32.CloseHandle(process_handle)

        return OSIsolationResult(
            mode="windows-job-object",
            enforced=True,
            memory_limit_bytes=self.memory_limit_bytes,
            process_limit=self.process_limit,
        )

    def terminate(self) -> None:
        if self._handle is None or self._kernel32 is None:
            return
        self._kernel32.TerminateJobObject(self._handle, 1)

    def close(self) -> None:
        if self._handle is None or self._kernel32 is None:
            return
        self._kernel32.CloseHandle(self._handle)
        self._handle = None


def native_isolation_mode() -> str:
    """Return the host-level isolation mechanism used by the process runner."""
    return "windows-job-object" if os.name == "nt" else "posix-rlimits"
