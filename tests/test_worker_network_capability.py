from __future__ import annotations

from pathlib import Path

import pytest

from agent_core.network_capability import NetworkCapabilityError
from agent_core.network_policy import NetworkPolicy
from agent_core.worker_isolation import WorkerIsolationPolicy
from worker_system.worker import Worker


def _worker() -> Worker:
    return Worker("test-worker", WorkerIsolationPolicy(Path.cwd()))


def test_worker_rejects_network_capability_escalation_before_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = _worker()

    def fail_executor(*args, **kwargs):
        raise AssertionError("executor must not start after capability escalation")

    monkeypatch.setattr("worker_system.worker.AgentExecutor", fail_executor)
    with pytest.raises(NetworkCapabilityError):
        worker.execute(
            {
                "task_id": "capability-escalation",
                "prompt": "inspect the workspace",
                "metadata": {
                    "mission_contract": {"network_access": "restricted"},
                    "network_access": "allow",
                },
            }
        )

    assert worker.status == "idle"


def test_worker_passes_authorized_capability_to_network_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = _worker()
    captured: dict[str, object] = {}

    class FakeExecutor:
        def __init__(self, service, network_policy=None, **kwargs):
            captured["network_policy"] = network_policy
            captured.update(kwargs)
            assert isinstance(network_policy, NetworkPolicy)
            assert network_policy.mode == "deny"

        def execute(self, prompt: str) -> dict[str, object]:
            return {
                "status": "completed",
                "execution_evidence": {"verified": True},
            }

    monkeypatch.setattr("worker_system.worker.AgentExecutor", FakeExecutor)
    monkeypatch.setattr("worker_system.worker.OllamaService", lambda **kwargs: object())

    result = worker.execute(
        {
            "task_id": "capability-restriction",
            "prompt": "inspect the workspace",
            "metadata": {
                "mission_contract": {"network_access": "restricted"},
                "network_access": "deny",
            },
        }
    )

    assert result["network_capability"]["contract_mode"] == "restricted"
    assert result["network_capability"]["requested_mode"] == "deny"
    assert result["network_capability"]["authorized_mode"] == "deny"
    assert result["network_capability"]["escalation_blocked"] is True
    assert "network_policy" in captured
