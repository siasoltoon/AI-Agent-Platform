import shutil

import pytest

from tool_system.terminal_tools import TerminalTool


def test_terminal_allows_python_version():
    result = TerminalTool().execute("python --version", timeout=10)
    assert result["code"] == 0
    assert result["timed_out"] is False


def test_terminal_allows_windows_type():
    result = TerminalTool().execute("type NUL", timeout=10)
    assert result["code"] == 0


def test_terminal_allows_directory_inspection():
    result = TerminalTool().execute("dir", timeout=10)
    assert result["code"] == 0


def test_terminal_allows_git_status():
    result = TerminalTool().execute("git status --short", timeout=10)
    assert result["code"] == 0


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed in this environment")
def test_terminal_allows_node_toolchain_command():
    result = TerminalTool().execute("node --version", timeout=10)
    assert result["code"] == 0


def test_terminal_rejects_shell_chaining():
    with pytest.raises(PermissionError, match="blocked operation"):
        TerminalTool().execute("python --version & echo unsafe")


def test_terminal_rejects_disallowed_executable():
    with pytest.raises(PermissionError, match="not allowed"):
        TerminalTool().execute("powershell Get-ChildItem")


def test_terminal_rejects_invalid_timeout():
    with pytest.raises(ValueError, match="between 1 and 600"):
        TerminalTool().execute("python --version", timeout=0)


def test_terminal_runs_commands_from_configured_workspace(tmp_path):
    result = TerminalTool(workspace_root=tmp_path).execute("python -c \"import os; print(os.getcwd())\"", timeout=10)
    assert result["code"] == 0
    assert str(tmp_path).lower() in result["stdout"].strip().lower()


def test_terminal_mkdir_cannot_escape_configured_workspace(tmp_path):
    with pytest.raises(PermissionError, match="escapes the configured workspace"):
        TerminalTool(workspace_root=tmp_path).execute("mkdir ../outside-agent-workspace")


def test_terminal_timeout_returns_structured_observation():
    result = TerminalTool().execute('python -c "import time; time.sleep(2)"', timeout=1)
    assert result["code"] == 124
    assert result["timed_out"] is True
    assert result["timeout_seconds"] == 1


def test_terminal_output_is_bounded():
    result = TerminalTool().execute('python -c "print(\'x\' * 20000)"', timeout=10)
    assert result["code"] == 0
    assert len(result["stdout"]) <= TerminalTool.MAX_OUTPUT_CHARS + 64
    assert "truncated" in result["stdout"]
