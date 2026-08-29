import pytest

from agent_core.runtime import AgentRuntime, MAX_RUNTIME_TIMEOUT


class FakeWorker:
    def __init__(self):
        self.calls = []

    def execute_task(self, payload, timeout):
        self.calls.append((payload, timeout))
        return {"result": "ok"}

    def health_check(self):
        return {"ok": True}


def test_runtime_rejects_timeout_above_hard_limit():
    worker = FakeWorker()
    runtime = AgentRuntime(worker_client=worker)

    with pytest.raises(ValueError, match="between 1 and 1800"):
        runtime.execute("hello", timeout_seconds=MAX_RUNTIME_TIMEOUT + 1)

    assert worker.calls == []


def test_runtime_uses_bounded_timeout_for_normal_task():
    worker = FakeWorker()
    runtime = AgentRuntime(worker_client=worker)

    result = runtime.execute("hello", timeout_seconds=30)

    assert result["execution_mode"] == "agentic"
    assert worker.calls[0][1] == 30
