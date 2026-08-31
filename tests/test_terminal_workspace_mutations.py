"""Regression coverage for idempotent terminal workspace mutations."""

from pathlib import Path

from tool_system.terminal_tools import TerminalTool


def test_mkdir_is_idempotent_when_directory_already_exists(tmp_path: Path):
    target = tmp_path / "telegram_bot"
    target.mkdir()

    result = TerminalTool().execute(f'mkdir "{target}"')

    assert result["code"] == 0
    assert result["timed_out"] is False
    assert target.is_dir()


def test_mkdir_creates_missing_nested_directories(tmp_path: Path):
    target = tmp_path / "telegram_bot" / "src" / "handlers"

    result = TerminalTool().execute(f'mkdir "{target}"')

    assert result["code"] == 0
    assert target.is_dir()
