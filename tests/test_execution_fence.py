from __future__ import annotations

import sqlite3

import pytest

from agent_core.execution_fence import ExecutionFence, ExecutionFenceError
from backend.storage.execution_ledger import ExecutionLedger
from backend.storage.side_effect_ledger import SideEffectLedger


def test_side_effect_is_idempotent_and_committed(tmp_path):
    db = tmp_path / "tasks.db"
    ledger = ExecutionLedger(db)
    effects = SideEffectLedger(db)
    ledger.begin("task-1", "worker-1", execution_id="exec-1")
    fence = ExecutionFence(task_id="task-1", execution_id="exec-1", fencing_token=1, ledger=ledger, side_effects=effects)

    key, first = fence.begin_side_effect("write_file", {"path": "a.txt", "content": "hello"})
    assert first["state"] == "running"
    assert fence.commit_side_effect(key, {"ok": True}) == {"ok": True}

    key2, replay = fence.begin_side_effect("write_file", {"path": "a.txt", "content": "hello"})
    assert key2 == key
    assert replay["state"] == "committed"
    assert replay["result_json"] is not None


def test_side_effect_idempotency_is_scoped_to_task(tmp_path):
    db = tmp_path / "tasks.db"
    ledger = ExecutionLedger(db)
    effects = SideEffectLedger(db)
    ledger.begin("task-1", "worker-1", execution_id="exec-1")
    ledger.begin("task-2", "worker-2", execution_id="exec-2")
    first = ExecutionFence(task_id="task-1", execution_id="exec-1", fencing_token=1, ledger=ledger, side_effects=effects)
    second = ExecutionFence(task_id="task-2", execution_id="exec-2", fencing_token=1, ledger=ledger, side_effects=effects)

    key1, _ = first.begin_side_effect("write_file", {"path": "a.txt", "content": "hello"})
    first.commit_side_effect(key1, {"task": "one"})
    key2, record2 = second.begin_side_effect("write_file", {"path": "a.txt", "content": "hello"})

    assert key2 != key1
    assert record2["state"] == "running"
    assert effects.get(key1)["task_id"] == "task-1"
    assert effects.get(key2)["task_id"] == "task-2"


def test_stale_execution_cannot_begin_side_effect(tmp_path):
    db = tmp_path / "tasks.db"
    ledger = ExecutionLedger(db)
    effects = SideEffectLedger(db)
    ledger.begin("task-1", "worker-1", execution_id="exec-1")
    ledger.begin("task-1", "worker-2", execution_id="exec-2")
    stale = ExecutionFence(task_id="task-1", execution_id="exec-1", fencing_token=1, ledger=ledger, side_effects=effects)

    with pytest.raises(ExecutionFenceError, match="no longer current"):
        stale.begin_side_effect("delete_file", {"path": "a.txt"})


def test_ambiguous_side_effect_is_not_replayed(tmp_path):
    db = tmp_path / "tasks.db"
    ledger = ExecutionLedger(db)
    effects = SideEffectLedger(db)
    ledger.begin("task-1", "worker-1", execution_id="exec-1")
    fence = ExecutionFence(task_id="task-1", execution_id="exec-1", fencing_token=1, ledger=ledger, side_effects=effects)
    key, _ = fence.begin_side_effect("move_file", {"source": "a", "destination": "b"})
    effects.transition(key, "ambiguous", error="worker disappeared")

    with pytest.raises(ExecutionFenceError, match="ambiguous"):
        fence.begin_side_effect("move_file", {"source": "a", "destination": "b"})


def test_side_effect_schema_is_durable(tmp_path):
    db = tmp_path / "tasks.db"
    SideEffectLedger(db)
    with sqlite3.connect(db) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(side_effects)")}
    assert {"idempotency_key", "execution_id", "fencing_token", "request_hash", "state", "result_json"} <= columns
