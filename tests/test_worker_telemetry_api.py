from backend.api import workers


def test_worker_record_exposes_live_resource_snapshot(monkeypatch):
    monkeypatch.setattr(
        workers.worker_client,
        "health_check",
        lambda: {
            "worker_id": "pc-worker-01",
            "worker_status": "idle",
            "resources": {
                "cpu_percent": 21.5,
                "ram_percent": 48.0,
                "gpu_percent": 12.0,
                "gpu_available": True,
            },
        },
    )

    record = workers._worker_record()

    assert record["worker_id"] == "pc-worker-01"
    assert record["status"] == "online"
    assert record["worker_status"] == "idle"
    assert record["resources"]["cpu_percent"] == 21.5
    assert record["resources"]["ram_percent"] == 48.0
    assert record["resources"]["gpu_percent"] == 12.0


def test_worker_record_is_offline_without_fabricated_telemetry(monkeypatch):
    monkeypatch.setattr(
        workers.worker_client,
        "health_check",
        lambda: (_ for _ in ()).throw(RuntimeError("connection failed")),
    )

    record = workers._worker_record()

    assert record["status"] == "offline"
    assert record["resources"] is None
