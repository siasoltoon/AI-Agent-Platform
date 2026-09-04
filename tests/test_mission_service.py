from agent_core.mission_service import MissionService


class FakeRuntime:
    default_model = "test-model"


def test_mission_service_exposes_professional_metadata(monkeypatch):
    service = MissionService(runtime=FakeRuntime())

    captured = {}

    def fake_run(mission_id, objective, max_retries=3):
        captured.update(mission_id=mission_id, objective=objective, max_retries=max_retries)
        return {"mission_id": mission_id, "status": "completed", "verified": True, "acceptance": {"accepted": True}}

    monkeypatch.setattr(service.orchestrator, "run", fake_run)
    result = service.execute("Implement a new authentication feature", task_id="m1", metadata={"max_retries": 2})

    assert result["execution_mode"] == "professional_mission"
    assert result["metadata"]["mission_mode"] == "professional"
    assert result["metadata"]["mission_contract"]["requires_tests"] is True
    assert captured == {"mission_id": "m1", "objective": "Implement a new authentication feature", "max_retries": 2}
