from pathlib import Path

import pytest

from agent_core.mission_contract import MissionContract
from agent_core.network_policy import NetworkPolicyError


def test_mission_contract_defaults_to_restricted_network():
    contract = MissionContract.from_objective("Implement a local feature and run tests")
    assert contract.network_access == "restricted"


def test_mission_contract_requires_explicit_network_capability():
    allowed = MissionContract.from_objective("Implement the integration and require network access")
    denied = MissionContract.from_objective("Audit the repository with no network access")
    assert allowed.network_access == "allow"
    assert denied.network_access == "deny"


def test_invalid_network_capability_is_rejected():
    with pytest.raises(ValueError):
        from agent_core.network_policy import NetworkPolicy
        NetworkPolicy(mode="anything")


def test_worker_propagates_mission_network_capability(monkeypatch, tmp_path: Path):
    import worker_system.worker as worker_module

    captured = {}

    class FakeExecutor:
        def __init__(self, service, workspace_root=None, max_steps=32, max_output_chars=12000, network_policy=None):
            captured["network_policy"] = network_policy
            captured["workspace_root"] = workspace_root

        def execute(self, prompt):
            return {
                "status": "completed",
                "execution_evidence": {"verified": True},
                "tool_records": [{"ok": True, "tool": "read_file", "result": {"path": "README.md"}}],
            }

    monkeypatch.setattr(worker_module, "AgentExecutor", FakeExecutor)
    worker = worker_module.Worker("test-worker", worker_module.WorkerIsolationPolicy(tmp_path))
    result = worker.execute({
        "task_id": "capability-test",
        "prompt": "Inspect the workspace",
        "model": "test-model",
        "metadata": {
            "workspace": str(tmp_path),
            "network_access": "deny",
        },
    })

    assert captured["network_policy"].mode == "deny"
    assert result["network_policy"]["mode"] == "deny"
    assert result["network_policy"]["enforcement"] == "terminal-command-policy"


def test_network_policy_rejects_explicit_interpreter_escape():
    policy = __import__("agent_core.network_policy", fromlist=["NetworkPolicy"]).NetworkPolicy(mode="restricted")
    with pytest.raises(NetworkPolicyError):
        policy.check_command("python", "python -c 'import socket; socket.create_connection((\"example.com\", 443))'")
