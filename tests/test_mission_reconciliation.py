from agent_core.mission_memory import MissionMemory, MissionMemoryStore
from agent_core.mission_reconciliation import MissionReconciler
from backend.storage.task_store import TaskStore


def _task(task_id: str, status: str = "queued") -> dict:
    return {
        "id": task_id,
        "prompt": "Implement authentication",
        "model": None,
        "status": status,
        "created_at": 1.0,
        "started_at": 2.0 if status == "running" else None,
        "completed_at": 3.0 if status == "completed" else None,
        "result": None,
        "error": None,
        "metadata": {"command": "mission.execute"},
    }


def _verified_memory(task_id: str) -> MissionMemory:
    memory = MissionMemory(task_id, "Implement authentication", status="completed")
    memory.record_execution({
        "mission_objective": memory.objective,
        "verified": True,
        "acceptance": {"accepted": True},
        "execution_evidence": {"tool_calls": 2, "successful_tool_calls": 2},
    })
    return memory


def _stores(tmp_path):
    task_store = TaskStore(tmp_path / "tasks.db")
    memory_store = MissionMemoryStore()
    return task_store, memory_store, MissionReconciler(task_store, memory_store)


def test_queued_professional_task_without_mission_creates_pending_mission(tmp_path):
    task_store, memory_store, reconciler = _stores(tmp_path)
    task_store.create(_task("m1"))

    result = reconciler.reconcile("m1")

    assert result.action == "mission_created"
    assert result.safe is True
    assert memory_store.load("m1").status == "pending"
    assert task_store.get("m1")["status"] == "queued"


def test_running_professional_task_without_mission_is_failed_not_replayed(tmp_path):
    task_store, _, reconciler = _stores(tmp_path)
    task_store.create(_task("m2", "running"))

    result = reconciler.reconcile("m2")

    assert result.action == "task_failed_missing_mission"
    assert result.safe is True
    assert task_store.get("m2")["status"] == "failed"


def test_verified_completed_mission_converges_stale_running_task(tmp_path):
    task_store, memory_store, reconciler = _stores(tmp_path)
    task_store.create(_task("m3", "running"))
    memory_store.save(_verified_memory("m3"))

    result = reconciler.reconcile("m3")

    assert result.action == "task_completed_from_verified_mission"
    assert result.converged is True
    task = task_store.get("m3")
    assert task["status"] == "completed"
    assert task["result"]["verified"] is True


def test_completed_mission_without_verification_never_becomes_task_success(tmp_path):
    task_store, memory_store, reconciler = _stores(tmp_path)
    task_store.create(_task("m4", "running"))
    memory = MissionMemory("m4", "Implement authentication", status="completed")
    memory.record_execution({"verified": False, "acceptance": {"accepted": False}})
    memory_store.save(memory)

    result = reconciler.reconcile("m4")

    assert result.action == "no_safe_convergence"
    assert result.converged is False
    assert task_store.get("m4")["status"] == "running"


def test_cancelled_mission_cancels_queued_task(tmp_path):
    task_store, memory_store, reconciler = _stores(tmp_path)
    task_store.create(_task("m5"))
    memory_store.save(MissionMemory("m5", "Implement authentication", status="cancelled"))

    result = reconciler.reconcile("m5")

    assert result.action == "task_cancelled_from_mission"
    assert task_store.get("m5")["status"] == "cancelled"


def test_cancelled_task_cancels_running_mission(tmp_path):
    task_store, memory_store, reconciler = _stores(tmp_path)
    task_store.create(_task("m6", "cancelled"))
    memory_store.save(MissionMemory("m6", "Implement authentication", status="running"))

    result = reconciler.reconcile("m6")

    assert result.action == "mission_cancelled_from_task"
    assert memory_store.load("m6").status == "cancelled"


def test_non_professional_task_is_ignored(tmp_path):
    task_store, _, reconciler = _stores(tmp_path)
    task = _task("generic")
    task["metadata"]["command"] = "agent.execute"
    task_store.create(task)

    result = reconciler.reconcile("generic")

    assert result.action == "ignored"
    assert result.converged is True
