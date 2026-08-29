from agent_core.large_task import LargeTaskOrchestrator


class FakeModel:
    def __init__(self):
        self.prompts = []

    def __call__(self, prompt, timeout):
        self.prompts.append(prompt)
        if "planning component" in prompt:
            return {"response": "1. Inspect requirements\n2. Implement solution\n3. Validate solution"}
        if "finalization component" in prompt:
            return {"response": "Final validated result"}
        return {"response": "Step completed"}


def test_large_task_runs_planning_execution_and_finalization():
    model = FakeModel()
    orchestrator = LargeTaskOrchestrator(
        generate=model,
        threshold=20,
        max_steps=3,
        max_retries=0,
        context_chars=1000,
        mission_context_chars=3000,
        mission_chunk_chars=1000,
    )

    result = orchestrator.execute("A" * 100, "test-model", 30)

    assert result["mode"] == "multi_step"
    assert result["steps"] == 3
    assert len(result["execution"]) == 3
    assert result["result"] == "Final validated result"
    assert any("planning component" in p for p in model.prompts)
    assert any("finalization component" in p for p in model.prompts)


def test_large_task_rejects_empty_step_result():
    def empty_model(prompt, timeout):
        if "planning component" in prompt:
            return {"response": "1. Do the work"}
        return {"response": ""}

    orchestrator = LargeTaskOrchestrator(
        generate=empty_model,
        threshold=5,
        max_retries=0,
    )

    try:
        orchestrator.execute("A" * 20, "test-model", 30)
    except RuntimeError as exc:
        assert "empty result" in str(exc)
    else:
        raise AssertionError("Expected empty step result to fail")
