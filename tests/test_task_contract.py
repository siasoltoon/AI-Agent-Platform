from pydantic import ValidationError

from task_engine.contracts import TaskRequest, TaskStatus


def test_task_request_accepts_large_prompt_without_arbitrary_rejection():
    prompt = "x" * 100_000
    request = TaskRequest(prompt=prompt)

    assert len(request.prompt) == 100_000
    assert request.model is None


def test_task_request_rejects_blank_prompt():
    try:
        TaskRequest(prompt="   ")
    except ValidationError:
        return

    raise AssertionError("Blank prompt should be rejected")


def test_task_request_normalizes_model():
    request = TaskRequest(prompt="hello", model="  qwen2.5-coder:7b  ")
    assert request.model == "qwen2.5-coder:7b"


def test_task_status_values_are_stable():
    assert TaskStatus.QUEUED.value == "queued"
    assert TaskStatus.RUNNING.value == "running"
    assert TaskStatus.COMPLETED.value == "completed"
    assert TaskStatus.FAILED.value == "failed"
    assert TaskStatus.CANCELLED.value == "cancelled"
