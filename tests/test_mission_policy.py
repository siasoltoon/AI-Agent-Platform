from agent_core.mission_policy import MissionPolicy


def test_read_only_detected_from_explicit_constraint():
    policy = MissionPolicy.from_task("Perform a read-only audit. Do not modify any files.")
    assert policy.read_only is True
    assert policy.allows_tool("read_file") is True
    assert policy.allows_tool("write_file", {"path": "x.txt"}) is False
    assert policy.allows_tool("delete_file", {"path": "x.txt"}) is False


def test_read_only_terminal_allows_observation_only():
    policy = MissionPolicy.from_task("Read-only repository inspection.")
    assert policy.allows_tool("terminal", {"command": "git status"}) is True
    assert policy.allows_tool("terminal", {"command": "dir"}) is True
    assert policy.allows_tool("terminal", {"command": "git rm x.txt"}) is True is False
