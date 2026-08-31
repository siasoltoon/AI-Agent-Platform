import time

from backend.services import telemetry


def test_snapshot_reports_cpu_and_ram_percent(monkeypatch):
    class Memory:
        percent = 37.5
        used = 100
        total = 200

    monkeypatch.setattr(telemetry.psutil, "cpu_percent", lambda interval=None: 42.5)
    monkeypatch.setattr(telemetry.psutil, "virtual_memory", lambda: Memory())
    monkeypatch.setattr(telemetry, "gpu_utilization_percent", lambda: (17.0, "test-gpu"))

    result = telemetry.snapshot()

    assert result["cpu_percent"] == 42.5
    assert result["ram_percent"] == 37.5
    assert result["gpu_percent"] == 17.0
    assert result["gpu_name"] == "test-gpu"
    assert result["gpu_available"] is True
    assert result["timestamp"] <= time.time()


def test_gpu_fallback_is_allowed_to_be_unavailable(monkeypatch):
    monkeypatch.setattr(telemetry, "_gpu_from_nvidia_smi", lambda: (None, None))
    monkeypatch.setattr(telemetry, "_gpu_from_windows_counters", lambda: (None, None))
    telemetry._gpu_cache = None

    value, name = telemetry.gpu_utilization_percent()

    assert value is None
    assert name is None
