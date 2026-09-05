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
