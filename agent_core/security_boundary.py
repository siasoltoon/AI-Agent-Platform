"""Deterministic workspace boundary for autonomous mission file access."""

from __future__ import annotations

import os
from pathlib import Path


class WorkspaceBoundary:
    """Resolve mission paths without allowing traversal or symlink escape."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).expanduser().resolve()

    def resolve(self, path: str | os.PathLike[str]) -> Path:
        candidate = Path(path)
        resolved = (self.root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise PermissionError(f"Path escapes mission workspace: {path}") from exc
        return resolved

    def assert_safe(self, path: str | os.PathLike[str]) -> Path:
        resolved = self.resolve(path)
        if resolved == self.root:
            return resolved
        current = resolved
        while current != self.root:
            if current.is_symlink():
                raise PermissionError(f"Symlink is not allowed in mission workspace path: {path}")
            current = current.parent
        return resolved
