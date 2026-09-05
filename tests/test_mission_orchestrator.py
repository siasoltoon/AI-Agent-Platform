from agent_core.checkpointed_runtime import CheckpointedRuntime
from agent_core.mission_memory import MissionMemoryStore
from agent_core.mission_orchestrator import MissionOrchestrator, MissionPhase


class FakeRuntime:
    def execute(self, prompt, *, task_id=None, **kwargs):
        return {"status": "completed"}


class FakeDeveloper:
    def __init__(self):
        self.calls = []
        self.runtime = FakeRuntime()
        self.memory_store = MissionMemoryStore()

    def run(self, mission_id, objective, max_retries=3, **kwargs):
        self.calls.append(("run", mission_id, objective, max_retries, kwargs))
        assert isinstance(kwargs["runtime"], CheckpointedRuntime)
        assert kwargs["runtime"].runtime is self.runtime
        return {
            "mission_id": mission_id,
            "status": "completed",
            "verified": True,
            "acceptance": {"accepted": True},
        }

    def cancel(self, mission_id):
        self.calls.append(("cancel", mission_id))
        return {"mission_id": mission_id, "status": "cancelled"}


def test_orchestrator_emits_contract_and_terminal_lifecycle():
    events = []
    developer = FakeDeveloper()
    orchestrator = MissionOrchestrator(developer, events.append)

    result = orchestrator.run("m1", "Implement a new authentication feature", max_retries=2)

    assert result["status"] == "completed"
    assert result["mission_contract"]["requires_tests"] is True
    assert developer.calls[0][:4] == ("run", "m1", "Implement a new authentication feature", 2)
    assert developer.runtime.__class__ is FakeRuntime
    assert [event.phase for event in events] == [
        MissionPhase.CONTRACT,
        MissionPhase.RECON,
        MissionPhase.PLAN,
        MissionPhase.EXECUTE,
        MissionPhase.VERIFY,
        MissionPhase.ACCEPT,
        MissionPhase.COMPLETE,
    ]


def test_orchestrator_propagates_execution_controls_without_mutating_developer():
    developer = FakeDeveloper()
    orchestrator = MissionOrchestrator(developer)

    orchestrator.run(
        "m-controls",
        "Implement a feature",
        model="test-model",
        timeout_seconds=123,
        metadata={"network_access": "restricted"},
    )

    kwargs = developer.calls[0][4]
    assert kwargs["model"] == "test-model"
    assert kwargs["timeout_seconds"] == 123
    assert kwargs["metadata"]["network_access"] == "restricted"
    assert developer.runtime.__class__ is FakeRuntime


def test_orchestrator_cancel_delegates_and_emits_terminal_event():
    events = []
    orchestrator = MissionOrchestrator(FakeDeveloper(), events.append)

    result = orchestrator.cancel("m2")

    assert result["status"] == "cancelled"
    assert events[-1].phase is MissionPhase.CANCELLED
