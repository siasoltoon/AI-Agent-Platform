"""Worker-level isolation policy for autonomous execution.

This is a host-process boundary, not a full OS sandbox. It guarantees that the
worker only accepts mission workspaces below one configured worker root and
rejects symlinked paths that could escape that root.
"""

from __future__ import annotations

from pathlib import Path


class WorkerIsolationError(PermissionError):
    """Raised when a task requests a workspace outside the worker boundary."""


class WorkerIsolationPolicy:
    """Enforce a single filesystem root for all worker execution workspaces."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise WorkerIsolationError(f"Worker isolation root must be an existing directory: {self.root}")

    def resolve_workspace(self, requested: str | Path | None = None) -> Path:
        candidate = self.root if requested is None or not str(requested).strip() else Path(requested).expanduser()
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise WorkerIsolationError(
                f"Requested workspace escapes worker isolation root: {requested}"
            ) from exc

        current = resolved
        while current != self.root:
            if current.is_symlink():
                raise WorkerIsolationError(
                    f"Symlinked workspace path is not allowed: {requested}"
                )
            current = current.parent
        return resolved

    def snapshot(self) -> dict[str, str]:
        return {"root": str(self.root), "mode": "worker-workspace-boundary", "os_sandbox": "not_provided"}
