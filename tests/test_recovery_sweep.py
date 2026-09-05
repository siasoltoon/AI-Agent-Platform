from agent_core.mission_memory import MissionMemory, MissionMemoryStore
from agent_core.mission_reconciliation import MissionReconciler
from backend.recovery_sweep import RecoverySweep
from backend.storage.task_store import TaskStore
from backend.storage.worker_lease_store import WorkerLeaseStore


def _task(task_id: str, *, status: str = "running", command: str = "agent.execute") -> dict:
    return {
        "id": task_id,
        "prompt": "Implement authentication",
        "model": None,
        "status": status,
        "created_at": 1.0,
        "started_at": 2.0 if status == "running" else None,
        "completed_at": None,
        "result": None,
        "error": None,
        "metadata": {"command": command},
    }


def _verified_memory(task_id: str) -> MissionMemory:
    memory = MissionMemory(task_id, "Implement authentication", status="completed")
    memory.record_execution({
        "mission_objective": memory.objective,
        "verified": True,
        "acceptance": {"accepted": True},
        "execution_evidence": {"tool_calls": 1, "successful_tool_calls": 1},
    })
    return memory


def test_live_lease_preserves_running_task(tmp_path):
    task_store = TaskStore(tmp_path / "tasks.db")
    lease_store = WorkerLeaseStore(tmp_path / "tasks.db")
    task_store.create(_task("live"))
    lease_store.acquire("live", "worker-a", "exec-a", ttl_seconds=30, now=100.0)

    result = RecoverySweep(task_store, lease_store).sweep(now=110.0)

    assert task_store.get("live")["status"] == "running"
    assert result["actions"][0]["action"] == "active_lease_preserved"


def test_orphaned_running_task_fails_instead_of_blind_replay(tmp_path):
    task_store = TaskStore(tmp_path / "tasks.db")
    lease_store = WorkerLeaseStore(tmp_path / "tasks.db")
    task_store.create(_task("orphan"))

    result = RecoverySweep(task_store, lease_store).sweep(now=110.0)

    task = task_store.get("orphan")
    assert task["status"] == "failed"
    assert task["metadata"]["automatic_retry_suppressed"] is True
    assert task["metadata"]["recovery_required"] is True
    assert result["actions"][0]["action"] == "orphaned_execution_failed"


def test_expired_execution_identity_is_preserved_for_forensics(tmp_path):
    task_store = TaskStore(tmp_path / "tasks.db")
    lease_store = WorkerLeaseStore(tmp_path / "tasks.db")
    task_store.create(_task("crashed"))
    lease_store.acquire("crashed", "worker-a", "exec-crashed", ttl_seconds=5, now=100.0)

    RecoverySweep(task_store, lease_store).sweep(now=110.0)

    task = task_store.get("crashed")
    assert task["status"] == "failed"
    assert task["metadata"]["orphaned_execution_id"] == "exec-crashed"
    assert lease_store.get("crashed") is None


def test_verified_professional_mission_repairs_stale_running_task(tmp_path):
    task_store = TaskStore(tmp_path / "tasks.db")
    lease_store = WorkerLeaseStore(tmp_path / "tasks.db")
    memory_store = MissionMemoryStore()
    reconciler = MissionReconciler(task_store, memory_store)
    task_store.create(_task("mission", command="mission.execute"))
    memory_store.save(_verified_memory("mission"))

    result = RecoverySweep(task_store, lease_store, reconciler).sweep(now=110.0)

    assert task_store.get("mission")["status"] == "completed"
    assert any(action["action"] == "task_completed_from_verified_mission" for action in result["actions"])
    assert not any(action["action"] == "orphaned_execution_failed" for action in result["actions"])


def test_unverified_professional_mission_is_not_auto_completed_or_replayed(tmp_path):
    task_store = TaskStore(tmp_path / "tasks.db")
    lease_store = WorkerLeaseStore(tmp_path / "tasks.db")
    memory_store = MissionMemoryStore()
    reconciler = MissionReconciler(task_store, memory_store)
    task_store.create(_task("ambiguous", command="mission.execute"))
    memory = MissionMemory("ambiguous", "Implement authentication", status="running")
    memory_store.save(memory)

    result = RecoverySweep(task_store, lease_store, reconciler).sweep(now=110.0)

    task = task_store.get("ambiguous")
    assert task["status"] == "failed"
    assert task["metadata"]["recovery_required"] is True
    assert any(action["action"] == "orphaned_execution_failed" for action in result["actions"])
