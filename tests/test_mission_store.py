from agent_core.mission_memory import MissionMemory, MissionMemoryStore
from backend.storage.mission_store import SQLiteMissionStore


def test_sqlite_mission_store_round_trips_complete_snapshot(tmp_path):
    store = SQLiteMissionStore(tmp_path / "missions.db")
    memory_store = MissionMemoryStore(store)
    memory = MissionMemory("m1", "Implement a feature")
    memory.record_event(phase="contract", status="completed", mission_id="m1")
    memory.completed.append("recon")
    memory.active_task = "implementation"
    memory.active_execution_id = "m1:implementation:1"

    memory_store.save(memory)
    restored = memory_store.load("m1")

    assert restored is not None
    assert restored.objective == "Implement a feature"
    assert restored.completed == ["recon"]
    assert restored.active_execution_id == "m1:implementation:1"
    assert restored.events[-1]["sequence"] == 1


def test_sqlite_mission_store_lists_bounded_status_filtered_snapshots(tmp_path):
    store = SQLiteMissionStore(tmp_path / "missions.db")
    for mission_id, status in (("m1", "completed"), ("m2", "blocked"), ("m3", "completed")):
        store.save_mission(mission_id, MissionMemory(mission_id, mission_id, status=status).snapshot())

    completed = store.list_missions(limit=1, status="completed")

    assert len(completed) == 1
    assert completed[0]["status"] == "completed"
