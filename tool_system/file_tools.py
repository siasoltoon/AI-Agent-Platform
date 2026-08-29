"""Bounded workspace file-system tools for the autonomous agent."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from .base_tool import BaseTool


class ReadFileTool(BaseTool):
    name = "read_file"

    def execute(self, path: str) -> str:
        target = Path(path)
        if not target.is_file():
            raise FileNotFoundError(f"File does not exist: {target}")
        return target.read_text(encoding="utf-8")


class WriteFileTool(BaseTool):
    name = "write_file"

    def execute(self, path: str, content: str) -> dict[str, Any]:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
        return {"ok": True, "path": str(target), "bytes": target.stat().st_size, "content": str(content)}


class FileExistsTool(BaseTool):
    name = "file_exists"

    def execute(self, path: str) -> dict[str, Any]:
        target = Path(path)
        return {"exists": target.is_file(), "path": str(target)}


class DirectoryExistsTool(BaseTool):
    name = "directory_exists"

    def execute(self, path: str) -> dict[str, Any]:
        target = Path(path)
        return {"exists": target.is_dir(), "path": str(target)}


class MakeDirectoryTool(BaseTool):
    name = "make_directory"

    def execute(self, path: str) -> dict[str, Any]:
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "path": str(target), "exists": target.is_dir()}


class ListDirectoryTool(BaseTool):
    name = "list_directory"

    def execute(self, path: str = ".") -> dict[str, Any]:
        target = Path(path)
        if not target.is_dir():
            raise FileNotFoundError(f"Directory does not exist: {target}")
        return {
            "path": str(target),
            "entries": [
                {
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                }
                for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            ],
        }


class SearchFilesTool(BaseTool):
    name = "search_files"

    def execute(self, path: str = ".", pattern: str = "*") -> dict[str, Any]:
        target = Path(path)
        if not target.is_dir():
            raise FileNotFoundError(f"Directory does not exist: {target}")
        matches = [str(p) for p in target.rglob(pattern) if p.is_file()]
        return {"path": str(target), "pattern": pattern, "matches": sorted(matches)[:2000]}


class CopyFileTool(BaseTool):
    name = "copy_file"

    def execute(self, source: str, destination: str) -> dict[str, Any]:
        src, dst = Path(source), Path(destination)
        if not src.is_file():
            raise FileNotFoundError(f"Source file does not exist: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return {"ok": True, "source": str(src), "destination": str(dst), "bytes": dst.stat().st_size}


class MoveFileTool(BaseTool):
    name = "move_file"

    def execute(self, source: str, destination: str) -> dict[str, Any]:
        src, dst = Path(source), Path(destination)
        if not src.exists():
            raise FileNotFoundError(f"Source does not exist: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"ok": True, "source": str(src), "destination": str(dst)}


class DeleteFileTool(BaseTool):
    name = "delete_file"

    def execute(self, path: str) -> dict[str, Any]:
        target = Path(path)
        if not target.is_file():
            raise FileNotFoundError(f"File does not exist: {target}")
        target.unlink()
        return {"ok": True, "path": str(target), "exists": target.exists()}


class FileHashTool(BaseTool):
    name = "file_hash"

    def execute(self, path: str, algorithm: str = "sha256") -> dict[str, Any]:
        target = Path(path)
        if not target.is_file():
            raise FileNotFoundError(f"File does not exist: {target}")
        algorithm = str(algorithm).lower()
        if algorithm not in {"md5", "sha1", "sha256", "sha512"}:
            raise ValueError("Unsupported hash algorithm.")
        digest = hashlib.new(algorithm)
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return {"ok": True, "path": str(target), "algorithm": algorithm, "hash": digest.hexdigest()}
