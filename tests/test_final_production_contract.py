from worker_system.worker import ExecuteRequest, MAX_AGENT_STEPS, MAX_METADATA_KEYS, MAX_PROMPT_CHARS


def test_worker_contract_accepts_bounded_execution_request():
    request = ExecuteRequest(
        prompt="Create a real file and verify it.",
        task_id="production-check",
        timeout=300,
        metadata={"max_agent_steps": MAX_AGENT_STEPS},
    )
    assert request.prompt == "Create a real file and verify it."
    assert request.task_id == "production-check"
    assert request.timeout == 300


def test_worker_contract_rejects_oversized_prompt():
    try:
        ExecuteRequest(prompt="x" * (MAX_PROMPT_CHARS + 1))
    except Exception as exc:
        assert "200000" in str(exc)
    else:
        raise AssertionError("Oversized prompt must be rejected.")


def test_worker_contract_rejects_excess_metadata_keys():
    metadata = {str(index): index for index in range(MAX_METADATA_KEYS + 1)}
    try:
        ExecuteRequest(prompt="ok", metadata=metadata)
    except Exception as exc:
        assert "64" in str(exc)
    else:
        raise AssertionError("Oversized metadata must be rejected.")
