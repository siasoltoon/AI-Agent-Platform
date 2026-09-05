import time

import pytest

from agent_core.execution_fence import ExecutionFence, ExecutionFenceError
from backend.storage.execution_ledger import ExecutionLedger
from backend.storage.side_effect_ledger import SideEffectLedger
from backend.storage.task_store import TaskStore
from task_engine.contracts import TaskStatus


def seed_running_task(store: TaskStore, task_id: str = "task-chaos") -> None:
    store.create({
        "id": task_id,
        "prompt": "chaos fence test",
        "model": None,
        "status": TaskStatus.QUEUED.value,
        "created_at": time.time(),
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "metadata": {"command": "agent.execute"},
    })
    assert store.claim_next_queued() is not None


def test_stale_execution_cannot_commit_after_newer_fence(tmp_path):
    db = tmp_path / "tasks.db"
    store = TaskStore(db)
    seed_running_task(store)
    ledger = ExecutionLedger(db)

    first = ledger.begin("task-chaos", "worker-a", execution_id="exec-a")
    second = ledger.begin("task-chaos", "worker-b", execution_id="exec-b")

    assert second["fencing_token"] > first["fencing_token"]
    assert ledger.fence_check("task-chaos", "exec-a", first["fencing_token"]) is False
    assert ledger.fence_check("task-chaos", "exec-b", second["fencing_token"]) is True
    assert ledger.commit_if_current("task-chaos", "exec-a", first["fencing_token"], result={"stale": True}) is False
    assert ledger.get("exec-a")["state"] == "superseded"
    assert ledger.commit_if_current("task-chaos", "exec-b", second["fencing_token"], result={"winner": "b"}) is True


def test_committed_replay_restores_only_when_attempt_is_still_current(tmp_path):
    db = tmp_path / "tasks.db"
    store = TaskStore(db)
    seed_running_task(store)
    ledger = ExecutionLedger(db)

    first = ledger.begin("task-chaos", "worker-a", execution_id="exec-a")
    assert ledger.commit_if_current("task-chaos", "exec-a", first["fencing_token"], result={"winner": "a"}) is True
    second = ledger.begin("task-chaos", "worker-b", execution_id="exec-b")

    restored = ledger.restore_committed_task_if_current(
        "task-chaos",
        "exec-a",
        first["fencing_token"],
        result={"winner": "a"},
        metadata={"execution_id": "exec-a", "fencing_token": first["fencing_token"], "idempotent_replay": True},
    )

    assert restored is False
    assert second["fencing_token"] > first["fencing_token"]
    assert store.get("task-chaos")["status"] == TaskStatus.RUNNING.value


def test_committed_replay_can_restore_same_current_attempt_atomically(tmp_path):
    db = tmp_path / "tasks.db"
    store = TaskStore(db)
    seed_running_task(store)
    ledger = ExecutionLedger(db)

    attempt = ledger.begin("task-chaos", "worker-a", execution_id="exec-a")
    assert ledger.commit_if_current("task-chaos", "exec-a", attempt["fencing_token"], result={"answer": 42}) is True

    restored = ledger.restore_committed_task_if_current(
        "task-chaos",
        "exec-a",
        attempt["fencing_token"],
        result={"answer": 42},
        metadata={"execution_id": "exec-a", "fencing_token": attempt["fencing_token"], "idempotent_replay": True},
    )

    assert restored is True
    assert store.get("task-chaos")["status"] == TaskStatus.COMPLETED.value
    assert store.get("task-chaos")["result"] == {"answer": 42}


def test_ambiguous_side_effect_is_never_replayed(tmp_path):
    db = tmp_path / "tasks.db"
    store = TaskStore(db)
    seed_running_task(store)
    ledger = ExecutionLedger(db)
    effects = SideEffectLedger(db)
    attempt = ledger.begin("task-chaos", "worker-a", execution_id="exec-a")
    fence = ExecutionFence(
        task_id="task-chaos",
        execution_id="exec-a",
        fencing_token=attempt["fencing_token"],
        ledger=ledger,
        side_effects=effects,
    )

    key, record = fence.begin_side_effect("file.write", {"path": "out.txt", "content": "hello"})
    assert record["state"] == "running"
    fence.mark_ambiguous(key, "worker crashed after external mutation")

    with pytest.raises(ExecutionFenceError, match="ambiguous"):
        fence.begin_side_effect("file.write", {"path": "out.txt", "content": "hello"})

    assert effects.get(key)["state"] == "ambiguous"


def test_committed_side_effect_is_replayed_from_ledger_without_execution(tmp_path):
    db = tmp_path / "tasks.db"
    store = TaskStore(db)
    seed_running_task(store)
    ledger = ExecutionLedger(db)
    effects = SideEffectLedger(db)
    attempt = ledger.begin("task-chaos", "worker-a", execution_id="exec-a")
    fence = ExecutionFence(
        task_id="task-chaos",
        execution_id="exec-a",
        fencing_token=attempt["fencing_token"],
        ledger=ledger,
        side_effects=effects,
    )

    arguments = {"path": "out.txt", "content": "hello"}
    key, _ = fence.begin_side_effect("file.write", arguments)
    fence.commit_side_effect(key, {"ok": True, "bytes": 5})

    replay_key, replay = fence.begin_side_effect("file.write", arguments)
    assert replay_key == key
    assert replay["state"] == "committed"
    assert replay["result_json"] is not None
