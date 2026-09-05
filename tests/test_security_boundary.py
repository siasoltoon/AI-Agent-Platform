import os

import pytest

from agent_core.security_boundary import WorkspaceBoundary


def test_workspace_boundary_rejects_parent_traversal(tmp_path):
    boundary = WorkspaceBoundary(tmp_path)
    with pytest.raises(PermissionError, match="escapes"):
        boundary.assert_safe("../outside.txt")


def test_workspace_boundary_rejects_absolute_path_outside_root(tmp_path):
    boundary = WorkspaceBoundary(tmp_path)
    outside = tmp_path.parent / "outside.txt"
    with pytest.raises(PermissionError, match="escapes"):
        boundary.assert_safe(outside)


def test_workspace_boundary_rejects_symlink_escape(tmp_path):
    boundary = WorkspaceBoundary(tmp_path)
    outside = tmp_path.parent / "outside-dir"
    outside.mkdir()
    link = tmp_path / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(PermissionError, match="escapes"):
        boundary.assert_safe("link/file.txt")
