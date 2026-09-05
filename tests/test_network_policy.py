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


def test_restricted_policy_blocks_python_network_module_escape():
    policy = NetworkPolicy("restricted")
    with pytest.raises(NetworkPolicyError):
        policy.check_command("python", "python -c \"import socket; socket.create_connection(('example.com', 80))\"")


def test_restricted_policy_blocks_node_network_api_escape():
    policy = NetworkPolicy("restricted")
    with pytest.raises(NetworkPolicyError):
        policy.check_command("node", "node -e \"fetch('https://example.com')\"")


def test_restricted_policy_allows_python_local_command():
    policy = NetworkPolicy("restricted")
    policy.check_command("python", "python -c \"print('local')\"")


def test_allow_policy_skips_interpreter_escape_detection():
    policy = NetworkPolicy("allow")
    policy.check_command("python", "python -c \"import socket; socket.create_connection(('example.com', 80))\"")


def test_terminal_reports_interpreter_escape_detection():
    result = TerminalTool().execute("echo hello")
    assert result["code"] == 0
    assert result["network_policy"]["interpreter_escape_detection"] is True
    assert result["network_policy"]["mode"] == "restricted"
    assert result["network_policy"]["enforcement"] == "terminal-command-policy"
