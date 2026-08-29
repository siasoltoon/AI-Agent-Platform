import pytest

from tool_system.terminal_tools import TerminalTool


def test_terminal_allows_python_version():
    result = TerminalTool().execute("python --version", timeout=10)
    assert result["code"] == 0
    assert result["timed_out"] is False


def test_terminal_rejects_shell_chaining():
    with pytest.raises(PermissionError, match="blocked operation"):
        TerminalTool().execute("python --version & echo unsafe")


def test_terminal_rejects_disallowed_executable():
    with pytest.raises(PermissionError, match="not allowed"):
        TerminalTool().execute("powershell Get-ChildItem")


def test_terminal_rejects_invalid_timeout():
    with pytest.raises(ValueError, match="between 1 and 600"):
        TerminalTool().execute("python --version", timeout=0)
