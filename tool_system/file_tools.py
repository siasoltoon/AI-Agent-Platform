from pathlib import Path
from .base_tool import BaseTool


class ReadFileTool(BaseTool):
    name = "read_file"

    def execute(self, path):
        return Path(path).read_text(encoding="utf-8")


class WriteFileTool(BaseTool):
    name = "write_file"

    def execute(self, path, content):
        Path(path).write_text(content, encoding="utf-8")
        return True
