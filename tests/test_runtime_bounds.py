import pytest

from agent_core.runtime import AgentRuntime, MAX_RUNTIME_TIMEOUT


class FakeWorker:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or {"result": "ok"}

    def execute_task(self, payload, timeout):
        self.calls.append((payload, timeout))
        return self.response

    def health_check(self):
        return {"ok": True}


def verified_worker_response():
    return {
        "status": "completed",
        "result": {
            "status": "completed",
            "execution_evidence": {"verified": True},
            "tool_records": [{"tool": "write_file", "ok": True}],
        },
    }


def test_runtime_rejects_timeout_above_hard_limit():
    worker = FakeWorker()
    runtime = AgentRuntime(worker_client=worker)

    with pytest.raises(ValueError, match="between 1 and 1800"):
        runtime.execute("hello", timeout_seconds=MAX_RUNTIME_TIMEOUT + 1)

    assert worker.calls == []


def test_runtime_uses_bounded_timeout_for_normal_task():
    worker = FakeWorker(verified_worker_response())
    runtime = AgentRuntime(worker_client=worker)

    result = runtime.execute("hello", timeout_seconds=30)

    assert result["execution_mode"] == "agentic"
    assert worker.calls[0][1] == 30
    assert worker.calls[0][0]["metadata"]["max_agent_steps"] == 32


def test_runtime_promotes_large_missions_to_one_real_agentic_execution():
    worker = FakeWorker(verified_worker_response())
    runtime = AgentRuntime(worker_client=worker)
    runtime.large_task_threshold = 10

    result = runtime.execute("this is a large mission", timeout_seconds=1800)

    assert result["execution_mode"] == "agentic_large"
    assert len(worker.calls) == 1
    payload, timeout = worker.calls[0]
    assert timeout == 1800
    assert payload["metadata"]["execution_profile"] == "large"
    assert payload["metadata"]["max_agent_steps"] == 32


def test_runtime_allows_large_mission_to_lower_its_step_budget():
    worker = FakeWorker(verified_worker_response())
    runtime = AgentRuntime(worker_client=worker)
    runtime.large_task_threshold = 10

    runtime.execute(
        "this is a large mission",
        timeout_seconds=120,
        metadata={"max_agent_steps": 8},
    )

    assert worker.calls[0][0]["metadata"]["max_agent_steps"] == 8


def test_runtime_rejects_large_mission_step_budget_above_safe_limit():
    worker = FakeWorker(verified_worker_response())
    runtime = AgentRuntime(worker_client=worker)
    runtime.large_task_threshold = 10

    with pytest.raises(ValueError, match="between 1 and 32"):
        runtime.execute("this is a large mission", metadata={"max_agent_steps": 33})

    assert worker.calls == []


def test_runtime_rejects_worker_claim_without_execution_evidence():
    worker = FakeWorker({
        "status": "completed",
        "result": "متاسفانه، من قادر به انجام این کار بر روی سیستم خودم نیستم.",
    })
    runtime = AgentRuntime(worker_client=worker)

    with pytest.raises(RuntimeError, match="verified execution evidence"):
        runtime.execute("Create hello.txt", timeout_seconds=30)
