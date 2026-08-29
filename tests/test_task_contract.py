import pytest
from pydantic import ValidationError

from task_engine.contracts import (
    MAX_METADATA_KEYS,
    MAX_PROMPT_CHARS,
    MAX_TASK_ID_CHARS,
    MAX_TIMEOUT_SECONDS,
    TaskRequest,
    TaskStatus,
)


def test_task_request_accepts_large_prompt_within_bound():
    prompt = "x" * 100_000
    request = TaskRequest(prompt=prompt)

    assert len(request.prompt) == 100_000
    assert request.model is None


def test_task_request_rejects_oversized_prompt():
    with pytest.raises(ValidationError):
        TaskRequest(prompt="x" * (MAX_PROMPT_CHARS + 1))


def test_task_request_rejects_blank_prompt():
    with pytest.raises(ValidationError):
        TaskRequest(prompt="   ")


def test_task_request_normalizes_model():
    request = TaskRequest(prompt="hello", model="  qwen2.5-coder:7b  ")
    assert request.model == "qwen2.5-coder:7b"


def test_task_request_normalizes_task_id():
    request = TaskRequest(prompt="hello", task_id="  task-123  ")
    assert request.task_id == "task-123"


def test_task_request_rejects_oversized_task_id():
    with pytest.raises(ValidationError):
        TaskRequest(prompt="hello", task_id="x" * (MAX_TASK_ID_CHARS + 1))


def test_task_request_enforces_timeout_boundaries():
    assert TaskRequest(prompt="hello", timeout_seconds=MAX_TIMEOUT_SECONDS).timeout_seconds == MAX_TIMEOUT_SECONDS

    with pytest.raises(ValidationError):
        TaskRequest(prompt="hello", timeout_seconds=MAX_TIMEOUT_SECONDS + 1)


def test_task_request_rejects_too_many_metadata_keys():
    metadata = {f"key-{i}": i for i in range(MAX_METADATA_KEYS + 1)}
    with pytest.raises(ValidationError):
        TaskRequest(prompt="hello", metadata=metadata)


def test_task_status_values_are_stable():
    assert TaskStatus.QUEUED.value == "queued"
    assert TaskStatus.RUNNING.value == "running"
    assert TaskStatus.COMPLETED.value == "completed"
    assert TaskStatus.FAILED.value == "failed"
    assert TaskStatus.CANCELLED.value == "cancelled"
