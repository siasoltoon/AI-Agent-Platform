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

    def _candidate(self, requested: str | Path | None) -> Path:
        if requested is None or not str(requested).strip():
            return self.root
        candidate = Path(requested).expanduser()
        return candidate if candidate.is_absolute() else self.root / candidate

    def _reject_symlink_components(self, candidate: Path) -> None:
        """Reject symlinks before resolution can erase the evidence of one."""
        try:
            relative = candidate.relative_to(self.root)
        except ValueError:
            return

        current = self.root
        for component in relative.parts:
            current = current / component
            if current.is_symlink():
                raise WorkerIsolationError(
                    f"Symlinked workspace path is not allowed: {candidate}"
                )

    def resolve_workspace(self, requested: str | Path | None = None) -> Path:
        candidate = self._candidate(requested)
        self._reject_symlink_components(candidate)
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise WorkerIsolationError(
                f"Requested workspace escapes worker isolation root: {requested}"
            ) from exc
        return resolved

    def snapshot(self) -> dict[str, str]:
        return {
            "root": str(self.root),
            "mode": "worker-workspace-boundary",
            "os_sandbox": "not_provided",
        }
