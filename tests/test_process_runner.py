import os
import sys

from tool_system.process_runner import IsolatedProcessRunner, ProcessLimits
from tool_system.terminal_tools import TerminalTool


def test_terminal_uses_argument_vector_without_shell(tmp_path):
    result = TerminalTool(workspace_root=tmp_path).execute("python --version", timeout=10)
    assert result["code"] == 0
    assert result["shell"] is False
    assert result["process_isolation"] == "new_process_group"


def test_terminal_environment_is_allowlisted(monkeypatch):
    monkeypatch.setenv("MISSION_TEST_SECRET_TOKEN", "must-not-leak")
    environment = TerminalTool._safe_environment()
    assert "MISSION_TEST_SECRET_TOKEN" not in environment
    assert all(key.upper() in TerminalTool._SAFE_ENV_KEYS for key in environment)


def test_process_runner_timeout_kills_process_group(tmp_path):
    runner = IsolatedProcessRunner(environment={"PATH": os.environ.get("PATH", "")})
    command = [sys.executable, "-c", "import time; time.sleep(10)"]
    stdout, stderr, code, timed_out = runner.run(
        command,
        cwd=str(tmp_path),
        limits=ProcessLimits(timeout_seconds=1, max_output_chars=1000),
    )
    assert stdout == ""
    assert code == 124
    assert timed_out is True
    assert "timed out" in stderr
