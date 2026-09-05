from pathlib import Path

import pytest

from agent_core.worker_isolation import WorkerIsolationError, WorkerIsolationPolicy


def test_worker_isolation_accepts_workspace_inside_root(tmp_path: Path):
    root = tmp_path / "worker"
    root.mkdir()
    workspace = root / "mission"
    workspace.mkdir()

    policy = WorkerIsolationPolicy(root)

    assert policy.resolve_workspace(workspace) == workspace.resolve()
    assert policy.resolve_workspace("mission") == workspace.resolve()


def test_worker_isolation_rejects_parent_escape(tmp_path: Path):
    root = tmp_path / "worker"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    policy = WorkerIsolationPolicy(root)

    with pytest.raises(WorkerIsolationError, match="escapes worker isolation root"):
        policy.resolve_workspace(outside)


def test_worker_isolation_rejects_symlink_escape(tmp_path: Path):
    root = tmp_path / "worker"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    policy = WorkerIsolationPolicy(root)

    with pytest.raises(WorkerIsolationError, match="Symlinked workspace path"):
        policy.resolve_workspace(link)


def test_worker_isolation_snapshot_declares_boundary(tmp_path: Path):
    root = tmp_path / "worker"
    root.mkdir()
    snapshot = WorkerIsolationPolicy(root).snapshot()

    assert snapshot["root"] == str(root.resolve())
    assert snapshot["mode"] == "worker-workspace-boundary"
    assert snapshot["os_sandbox"] == "not_provided"
