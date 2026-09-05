import os

from agent_core.os_isolation import OSIsolationResult, WindowsJobIsolation, native_isolation_mode
from tool_system.process_runner import IsolatedProcessRunner, ProcessLimits


def test_native_isolation_mode_matches_host():
    expected = "windows-job-object" if os.name == "nt" else "posix-rlimits"
    assert native_isolation_mode() == expected
    assert IsolatedProcessRunner.isolation_mode() == expected


def test_non_windows_job_isolation_reports_posix_fallback():
    if os.name == "nt":
        return
    result = WindowsJobIsolation(memory_limit_bytes=1024, process_limit=2).attach(type("Process", (), {"pid": 1})())
    assert isinstance(result, OSIsolationResult)
    assert result.mode == "posix-rlimits"
    assert result.enforced is False
    assert result.memory_limit_bytes == 1024
    assert result.process_limit == 2


def test_os_isolation_result_snapshot_is_machine_readable():
    result = OSIsolationResult(
        mode="windows-job-object",
        enforced=True,
        memory_limit_bytes=2048,
        process_limit=4,
    )
    assert result.snapshot() == {
        "mode": "windows-job-object",
        "enforced": True,
        "memory_limit_bytes": 2048,
        "process_limit": 4,
    }


def test_process_limits_remain_explicit_for_native_containment():
    limits = ProcessLimits(timeout_seconds=5, max_output_chars=1000, max_memory_bytes=4096, max_processes=3)
    assert limits.max_memory_bytes == 4096
    assert limits.max_processes == 3
