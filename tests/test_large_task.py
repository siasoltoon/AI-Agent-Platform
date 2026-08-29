from agent_core.large_task import LargeTaskOrchestrator


def test_large_task_planning_and_execution():
    calls = []

    def generate(prompt, timeout):
        calls.append(prompt)
        if "Return ONLY a numbered list" in prompt:
            return {"response": "1. Analyze the mission\n2. Produce the implementation"}
        if "finalization component" in prompt:
            return {"response": "Final answer"}
        return {"response": "Step complete"}

    orchestrator = LargeTaskOrchestrator(
        generate=generate,
        threshold=10,
        max_steps=4,
        context_chars=2000,
    )

    result = orchestrator.execute(
        prompt="This is a sufficiently large mission.",
        model="qwen2.5-coder:7b",
        timeout=60,
    )

    assert result["mode"] == "multi_step"
    assert result["steps"] == 2
    assert result["result"] == "Final answer"
    assert len(calls) == 4


def test_small_task_stays_single_call():
    calls = []

    def generate(prompt, timeout):
        calls.append(prompt)
        return {"response": "small result"}

    orchestrator = LargeTaskOrchestrator(
        generate=generate,
        threshold=100,
    )

    result = orchestrator.execute(
        prompt="small",
        model="qwen2.5-coder:7b",
        timeout=60,
    )

    assert result["mode"] == "single"
    assert result["steps"] == 1
    assert result["result"] == "small result"
    assert len(calls) == 1
