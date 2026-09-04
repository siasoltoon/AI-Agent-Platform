from pathlib import Path

import pytest

from tool_system.file_tools import DeleteFileTool, ReadFileTool, WriteFileTool
from tool_system.terminal_tools import TerminalTool


def test_file_tools_reject_parent_traversal(tmp_path: Path):
    tool = WriteFileTool(workspace_root=tmp_path)
    with pytest.raises(PermissionError, match="escapes the configured workspace"):
        tool.execute("../outside.txt", "blocked")


def test_file_tools_reject_absolute_outside_path(tmp_path: Path):
    tool = ReadFileTool(workspace_root=tmp_path)
    outside = tmp_path.parent / "outside-agent-boundary.txt"
    with pytest.raises(PermissionError, match="escapes the configured workspace"):
        tool.execute(str(outside))


def test_file_tools_reject_symlink_escape(tmp_path: Path):
    outside = tmp_path.parent / "outside-target"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are unavailable in this environment")
    with pytest.raises(PermissionError, match="escapes the configured workspace|Symlink is not allowed"):
        ReadFileTool(workspace_root=tmp_path).execute(str(link / "secret.txt"))


def test_file_tools_reject_symlink_delete_target(tmp_path: Path):
    outside = tmp_path.parent / "outside-delete-target.txt"
    outside.write_text("protected", encoding="utf-8")
    link = tmp_path / "delete-link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are unavailable in this environment")
    with pytest.raises(PermissionError, match="escapes the configured workspace|Symlink is not allowed"):
        DeleteFileTool(workspace_root=tmp_path).execute(str(link))
    assert outside.exists()


def test_terminal_type_rejects_outside_path(tmp_path: Path):
    outside = tmp_path.parent / "terminal-outside.txt"
    outside.write_text("protected", encoding="utf-8")
    with pytest.raises(PermissionError, match="escapes the configured workspace|Symlink is not allowed"):
        TerminalTool(workspace_root=tmp_path).execute(f'type "{outside}"')


def test_terminal_filters_secret_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_TEST_TOKEN", "must-not-leak")
    result = TerminalTool(workspace_root=tmp_path).execute('python -c "import os; print(os.getenv(\'AGENT_TEST_TOKEN\', \'MISSING\'))"')
    assert result["code"] == 0
    assert "must-not-leak" not in result["stdout"]
    assert "MISSING" in result["stdout"]
