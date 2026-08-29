import pytest
from pydantic import ValidationError

from worker_system.worker import (
    MAX_AGENT_STEPS,
    MAX_METADATA_KEYS,
    MAX_MODEL_CHARS,
    MAX_PROMPT_CHARS,
    MAX_TASK_ID_CHARS,
    MAX_TIMEOUT_SECONDS,
    ExecuteRequest,
)


def test_worker_request_accepts_contract_boundaries():
    request = ExecuteRequest(
        prompt="x" * MAX_PROMPT_CHARS,
        model="m" * MAX_MODEL_CHARS,
        task_id="t" * MAX_TASK_ID_CHARS,
        timeout=MAX_TIMEOUT_SECONDS,
        metadata={f"k{i}": i for i in range(MAX_METADATA_KEYS)},
    )
    assert len(request.prompt) == MAX_PROMPT_CHARS
    assert len(request.model) == MAX_MODEL_CHARS
    assert len(request.task_id) == MAX_TASK_ID_CHARS
    assert request.timeout == MAX_TIMEOUT_SECONDS


def test_worker_request_rejects_oversized_prompt():
    with pytest.raises(ValidationError):
        ExecuteRequest(prompt="x" * (MAX_PROMPT_CHARS + 1))


def test_worker_request_rejects_oversized_model():
    with pytest.raises(ValidationError):
        ExecuteRequest(prompt="hello", model="x" * (MAX_MODEL_CHARS + 1))


def test_worker_request_rejects_oversized_task_id():
    with pytest.raises(ValidationError):
        ExecuteRequest(prompt="hello", task_id="x" * (MAX_TASK_ID_CHARS + 1))


def test_worker_request_rejects_timeout_outside_contract():
    with pytest.raises(ValidationError):
        ExecuteRequest(prompt="hello", timeout=MAX_TIMEOUT_SECONDS + 1)


def test_worker_request_rejects_too_many_metadata_keys():
    with pytest.raises(ValidationError):
        ExecuteRequest(prompt="hello", metadata={f"k{i}": i for i in range(MAX_METADATA_KEYS + 1)})


def test_worker_agent_steps_are_explicitly_bounded():
    assert MAX_AGENT_STEPS == 32
