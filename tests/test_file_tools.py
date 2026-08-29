from pathlib import Path

from tool_system.file_tools import DeleteFileTool, FileExistsTool, ListDirectoryTool, ReadFileTool, WriteFileTool


def test_write_and_read_file(tmp_path: Path):
    path = tmp_path / "nested" / "hello.txt"
    WriteFileTool().execute(str(path), "Hello World")
    assert ReadFileTool().execute(str(path)) == "Hello World"


def test_file_exists_tool(tmp_path: Path):
    path = tmp_path / "hello.txt"
    assert FileExistsTool().execute(str(path))["exists"] is False
    path.write_text("ok", encoding="utf-8")
    assert FileExistsTool().execute(str(path))["exists"] is True


def test_list_directory_tool(tmp_path: Path):
    (tmp_path / "folder").mkdir()
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    result = ListDirectoryTool().execute(str(tmp_path))
    names = {entry["name"] for entry in result["entries"]}
    assert names == {"folder", "file.txt"}


def test_delete_file_tool(tmp_path: Path):
    path = tmp_path / "delete-me.txt"
    path.write_text("x", encoding="utf-8")
    result = DeleteFileTool().execute(str(path))
    assert result["ok"] is True
    assert not path.exists()
