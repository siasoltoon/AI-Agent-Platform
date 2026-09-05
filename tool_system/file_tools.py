"""Bounded workspace file-system tools for the autonomous agent."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from agent_core.execution_fence import ExecutionFence
from agent_core.security_boundary import WorkspaceBoundary
from .base_tool import BaseTool


class _WorkspaceFileTool(BaseTool):
    """Common workspace boundary and optional execution fence."""
    def __init__(self, workspace_root: str | Path | None = None, execution_fence: ExecutionFence | None = None) -> None:
        self._boundary = WorkspaceBoundary(workspace_root) if workspace_root is not None else None
        self.execution_fence = execution_fence

    def _path(self, path: str | Path) -> Path:
        return self._boundary.assert_safe(path) if self._boundary is not None else Path(path)

    def _fence(self, arguments: Any) -> str | None:
        if self.execution_fence is None:
            return None
        key, _ = self.execution_fence.begin_side_effect(self.name, arguments)
        return key

    def _replay(self, key: str | None) -> Any | None:
        if self.execution_fence is None or key is None:
            return None
        record = self.execution_fence.side_effects.get(key)
        if record and record.get("state") == "committed" and record.get("result_json") is not None:
            return json.loads(record["result_json"])
        return None

    def _commit(self, key: str | None, result: Any) -> Any:
        if self.execution_fence is None or key is None:
            return result
        return self.execution_fence.commit_side_effect(key, result)

    def _ambiguous(self, key: str | None, error: str) -> None:
        if self.execution_fence is not None and key is not None:
            self.execution_fence.mark_ambiguous(key, error)

    def _failed(self, key: str | None, error: str) -> None:
        if self.execution_fence is not None and key is not None:
            self.execution_fence.side_effects.transition(key, "failed", error=error)

    def _assert_current(self) -> None:
        if self.execution_fence is not None:
            self.execution_fence.assert_current()


class ReadFileTool(_WorkspaceFileTool):
    name = "read_file"

    def execute(self, path: str) -> str:
        target = self._path(path)
        if not target.is_file():
            raise FileNotFoundError(f"File does not exist: {target}")
        return target.read_text(encoding="utf-8")


class WriteFileTool(_WorkspaceFileTool):
    name = "write_file"

    def execute(self, path: str, content: str) -> dict[str, Any]:
        target = self._path(path)
        key = self._fence({"path": str(target), "content": str(content)})
        replay = self._replay(key)
        if replay is not None:
            return replay
        self._assert_current()
        mutation_started = False
        try:
            mutation_started = True
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")
            return self._commit(key, {"ok": True, "path": str(target), "bytes": target.stat().st_size, "content": str(content)})
        except Exception as exc:
            if mutation_started:
                self._ambiguous(key, str(exc))
            else:
                self._failed(key, str(exc))
            raise


class FileExistsTool(_WorkspaceFileTool):
    name = "file_exists"

    def execute(self, path: str) -> dict[str, Any]:
        target = self._path(path)
        return {"exists": target.is_file(), "path": str(target)}


class DirectoryExistsTool(_WorkspaceFileTool):
    name = "directory_exists"

    def execute(self, path: str) -> dict[str, Any]:
        target = self._path(path)
        return {"exists": target.is_dir(), "path": str(target)}


class ListDirectoryTool(_WorkspaceFileTool):
    name = "list_directory"

    def execute(self, path: str = ".") -> dict[str, Any]:
        target = self._path(path)
        if not target.is_dir():
            raise FileNotFoundError(f"Directory does not exist: {target}")
        return {"path": str(target), "entries": [{"name": item.name, "type": "directory" if item.is_dir() else "file", "size": item.stat().st_size if item.is_file() else None} for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))]}


class SearchFilesTool(_WorkspaceFileTool):
    name = "search_files"

    def execute(self, path: str = ".", pattern: str = "*") -> dict[str, Any]:
        target = self._path(path)
        if not target.is_dir():
            raise FileNotFoundError(f"Directory does not exist: {target}")
        return {"path": str(target), "pattern": pattern, "matches": sorted(str(p) for p in target.rglob(pattern) if p.is_file())[:2000]}


class CopyFileTool(_WorkspaceFileTool):
    name = "copy_file"

    def execute(self, source: str, destination: str) -> dict[str, Any]:
        src, dst = self._path(source), self._path(destination)
        key = self._fence({"source": str(src), "destination": str(dst)})
        replay = self._replay(key)
        if replay is not None:
            return replay
        self._assert_current()
        if not src.is_file():
            self._failed(key, f"Source file does not exist: {src}")
            raise FileNotFoundError(f"Source file does not exist: {src}")
        mutation_started = False
        try:
            mutation_started = True
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return self._commit(key, {"ok": True, "source": str(src), "destination": str(dst), "bytes": dst.stat().st_size})
        except Exception as exc:
            if mutation_started:
                self._ambiguous(key, str(exc))
            else:
                self._failed(key, str(exc))
            raise


class MoveFileTool(_WorkspaceFileTool):
    name = "move_file"

    def execute(self, source: str, destination: str) -> dict[str, Any]:
        src, dst = self._path(source), self._path(destination)
        key = self._fence({"source": str(src), "destination": str(dst)})
        replay = self._replay(key)
        if replay is not None:
            return replay
        self._assert_current()
        if not src.exists():
            self._failed(key, f"Source does not exist: {src}")
            raise FileNotFoundError(f"Source does not exist: {src}")
        mutation_started = False
        try:
            mutation_started = True
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return self._commit(key, {"ok": True, "source": str(src), "destination": str(dst)})
        except Exception as exc:
            if mutation_started:
                self._ambiguous(key, str(exc))
            else:
                self._failed(key, str(exc))
            raise


class DeleteFileTool(_WorkspaceFileTool):
    name = "delete_file"

    def execute(self, path: str) -> dict[str, Any]:
        target = self._path(path)
        key = self._fence({"path": str(target)})
        replay = self._replay(key)
        if replay is not None:
            return replay
        self._assert_current()
        if not target.is_file():
            self._failed(key, f"File does not exist: {target}")
            raise FileNotFoundError(f"File does not exist: {target}")
        mutation_started = False
        try:
            mutation_started = True
            target.unlink()
            return self._commit(key, {"ok": True, "path": str(target), "exists": target.exists()})
        except Exception as exc:
            if mutation_started:
                self._ambiguous(key, str(exc))
            else:
                self._failed(key, str(exc))
            raise


class MakeDirectoryTool(_WorkspaceFileTool):
    name = "make_directory"

    def execute(self, path: str) -> dict[str, Any]:
        target = self._path(path)
        key = self._fence({"path": str(target)})
        replay = self._replay(key)
        if replay is not None:
            return replay
        self._assert_current()
        mutation_started = False
        try:
            mutation_started = True
            target.mkdir(parents=True, exist_ok=True)
            return self._commit(key, {"ok": True, "path": str(target), "exists": target.is_dir()})
        except Exception as exc:
            if mutation_started:
                self._ambiguous(key, str(exc))
            else:
                self._failed(key, str(exc))
            raise


class FileHashTool(_WorkspaceFileTool):
    name = "file_hash"

    def execute(self, path: str, algorithm: str = "sha256") -> dict[str, Any]:
        target = self._path(path)
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
