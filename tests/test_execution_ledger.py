from backend.storage.execution_ledger import ExecutionLedger


def test_begin_assigns_monotonic_fencing_tokens(tmp_path):
    ledger = ExecutionLedger(tmp_path / "tasks.db")
    first = ledger.begin("task-1", "worker-a")
    second = ledger.begin("task-1", "worker-b")

    assert first["attempt_no"] == 1
    assert second["attempt_no"] == 2
    assert second["fencing_token"] > first["fencing_token"]
    assert ledger.get(first["execution_id"])["state"] == "superseded"


def test_idempotency_key_returns_existing_attempt(tmp_path):
    ledger = ExecutionLedger(tmp_path / "tasks.db")
    first = ledger.begin("task-1", "worker-a", idempotency_key="request-1")
    second = ledger.begin("task-1", "worker-b", idempotency_key="request-1")

    assert second["execution_id"] == first["execution_id"]
    assert second["attempt_no"] == first["attempt_no"]


def test_stale_execution_cannot_commit_after_fencing(tmp_path):
    ledger = ExecutionLedger(tmp_path / "tasks.db")
    first = ledger.begin("task-1", "worker-a")
    second = ledger.begin("task-1", "worker-b")

    assert not ledger.fence_check("task-1", first["execution_id"], first["fencing_token"])
    assert not ledger.commit_if_current("task-1", first["execution_id"], first["fencing_token"])
    assert ledger.commit_if_current("task-1", second["execution_id"], second["fencing_token"])
    assert ledger.current("task-1")["state"] == "committed"


def test_ambiguous_attempt_is_not_auto_committed(tmp_path):
    ledger = ExecutionLedger(tmp_path / "tasks.db")
    attempt = ledger.begin("task-1", "worker-a")
    assert ledger.transition(attempt["execution_id"], "ambiguous", error="worker timeout")
    assert ledger.current("task-1")["state"] == "ambiguous"
