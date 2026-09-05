from agent_core.mission_memory import MissionMemory
from agent_core.mission_service import MissionService


class FakeRuntime:
    default_model = "test-model"


def test_mission_service_exposes_professional_metadata(monkeypatch):
    service = MissionService(runtime=FakeRuntime())

    captured = {}

    def fake_run(mission_id, objective, max_retries=3, **kwargs):
        captured.update(
            mission_id=mission_id,
            objective=objective,
            max_retries=max_retries,
            kwargs=kwargs,
        )
        return {"mission_id": mission_id, "status": "completed", "verified": True, "acceptance": {"accepted": True}}

    monkeypatch.setattr(service.orchestrator, "run", fake_run)
    result = service.execute("Implement a new authentication feature", task_id="m1", metadata={"max_retries": 2})

    assert result["execution_mode"] == "professional_mission"
    assert result["metadata"]["mission_mode"] == "professional"
    assert result["metadata"]["mission_contract"]["requires_tests"] is True
    assert result["metadata"]["network_access"] == "restricted"
    assert captured["mission_id"] == "m1"
    assert captured["objective"] == "Implement a new authentication feature"
    assert captured["max_retries"] == 2
    assert captured["kwargs"]["model"] is None
    assert captured["kwargs"]["timeout_seconds"] is None
    assert captured["kwargs"]["metadata"]["network_access"] == "restricted"


def test_mission_service_inspect_returns_bounded_ordered_event_history():
    service = MissionService(runtime=FakeRuntime())
    memory = MissionMemory("m1", "Implement a feature")
    memory.record_event(phase="contract", status="completed", mission_id="m1")
    memory.record_event(phase="plan", status="delegated", mission_id="m1")
    memory.record_event(phase="execute", status="delegated", mission_id="m1")
    service.developer.memory_store.save(memory)

    snapshot = service.inspect("m1", event_limit=2)

    assert snapshot["mission_id"] == "m1"
    assert snapshot["event_count"] == 3
    assert snapshot["events_truncated"] is True
    assert [event["sequence"] for event in snapshot["events"]] == [2, 3]


def test_mission_service_inspect_rejects_invalid_event_limit():
    service = MissionService(runtime=FakeRuntime())

    for limit in (0, 1001):
        try:
            service.inspect("m1", event_limit=limit)
        except ValueError as exc:
            assert "event_limit" in str(exc)
        else:
            raise AssertionError("invalid event_limit should fail")


def test_mission_service_cancel_persists_memory_when_task_has_not_started():
    service = MissionService(runtime=FakeRuntime())

    result = service.cancel("queued-mission", objective="Implement a feature")

    assert result["status"] == "cancelled"
    memory = service.developer.memory_store.load("queued-mission")
    assert memory is not None
    assert memory.status == "cancelled"
    assert memory.events[-1]["phase"] == "cancelled"
    assert memory.events[-1]["status"] == "cancelled"
