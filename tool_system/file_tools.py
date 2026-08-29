from pathlib import Path

from .base_tool import BaseTool


class ReadFileTool(BaseTool):
    name = "read_file"

    def execute(self, path):
        return Path(path).read_text(encoding="utf-8")


class WriteFileTool(BaseTool):
    name = "write_file"

    def execute(self, path, content):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return True


class FileExistsTool(BaseTool):
    name = "file_exists"

    def execute(self, path):
        target = Path(path)
        return {"exists": target.is_file(), "path": str(target)}


class ListDirectoryTool(BaseTool):
    name = "list_directory"

    def execute(self, path="."):
        target = Path(path)
        if not target.is_dir():
            raise FileNotFoundError(f"Directory does not exist: {target}")
        return {
            "path": str(target),
            "entries": [
                {"name": item.name, "type": "directory" if item.is_dir() else "file"}
                for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            ],
        }


class DeleteFileTool(BaseTool):
    name = "delete_file"

    def execute(self, path):
        target = Path(path)
        if not target.is_file():
            raise FileNotFoundError(f"File does not exist: {target}")
        target.unlink()
        return {"ok": True, "path": str(target)}
