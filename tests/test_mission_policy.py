from agent_core.mission_policy import MissionPolicy


def test_read_only_detected_from_explicit_constraints():
    for task in (
        "Perform a read-only audit. Do not modify any files.",
        "Inspect only; make no changes.",
        "Review the repository without making changes.",
        "Do not alter the workspace.",
    ):
        assert MissionPolicy.from_task(task).read_only is True


def test_target_write_exception_is_not_misclassified_as_read_only():
    task = (
        "Create agent-full-e2e.txt with exactly: expected. "
        "Do not modify or delete any other files."
    )
    policy = MissionPolicy.from_task(task)
    assert policy.read_only is False


def test_read_only_allows_observation_tools():
    policy = MissionPolicy.from_task("Read-only repository inspection.")
    for tool in ("read_file", "file_exists", "directory_exists", "list_directory", "search_files", "file_hash"):
        assert policy.allows_tool(tool) is True


def test_read_only_blocks_all_mutating_tools():
    policy = MissionPolicy.from_task("Perform a read-only audit.")
    for tool in ("write_file", "make_directory", "copy_file", "move_file", "delete_file"):
        assert policy.allows_tool(tool, {"path": "x.txt"}) is False


def test_read_only_blocks_terminal_completely():
    policy = MissionPolicy.from_task("Read-only repository inspection.")
    for command in ("dir", "git status", "git commit -am bad", "python -c print(1)", "powershell Remove-Item x.txt"):
        assert policy.allows_tool("terminal", {"command": command}) is False


def test_normal_mission_keeps_mutation_capability():
    policy = MissionPolicy.from_task("Create x.txt with hello")
    assert policy.read_only is False
    assert policy.allows_tool("write_file", {"path": "x.txt"}) is True
    assert policy.allows_tool("terminal", {"command": "git status"}) is True


def test_policy_evidence_marks_violation_noncompliant():
    policy = MissionPolicy.from_task("Read-only audit.")
    records = [{
        "step": 2,
        "tool": "write_file",
        "ok": False,
        "policy_violation": True,
        "error": "blocked",
    }]
    evidence = policy.evidence(records)
    assert evidence["read_only"] is True
    assert evidence["compliant"] is False
    assert evidence["unauthorized_mutations"] == 0
    assert evidence["policy_violations"][0]["tool"] == "write_file"
