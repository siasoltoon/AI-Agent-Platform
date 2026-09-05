import pytest

from agent_core.network_policy import NetworkPolicy, NetworkPolicyError
from tool_system.terminal_tools import TerminalTool


def test_restricted_policy_blocks_direct_network_commands():
    policy = NetworkPolicy("restricted")
    with pytest.raises(NetworkPolicyError):
        policy.check_command("curl")


def test_restricted_policy_allows_local_toolchain_commands():
    policy = NetworkPolicy("restricted")
    policy.check_command("pytest")
    policy.check_command("git")


def test_deny_policy_blocks_package_network_tools():
    policy = NetworkPolicy("deny")
    with pytest.raises(NetworkPolicyError):
        policy.check_command("pip")


def test_allow_policy_permits_network_command():
    policy = NetworkPolicy("allow")
    policy.check_command("curl")
    assert policy.evidence("curl", allowed=True)["allowed"] is True


def test_invalid_network_policy_mode_is_rejected():
    with pytest.raises(ValueError):
        NetworkPolicy("unknown")


def test_terminal_reports_network_policy():
    result = TerminalTool().execute("echo hello")
    assert result["code"] == 0
    assert result["network_policy"]["mode"] == "restricted"
    assert result["network_policy"]["enforcement"] == "terminal-command-policy"
