"""Cross-platform host resource telemetry for the execution worker.

CPU and RAM come from psutil. GPU utilization prefers nvidia-smi when available
and falls back to Windows GPU Engine performance counters, which also supports
AMD/Intel adapters. Telemetry is observational only and never blocks task
execution when a GPU provider is unavailable.
"""

from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
import time
from typing import Any

import psutil


_GPU_CACHE_SECONDS = 1.5
_gpu_cache: tuple[float, float | None, str | None] | None = None


def _gpu_from_nvidia_smi() -> tuple[float | None, str | None]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None, None
    try:
        completed = subprocess.run(
            [executable, "--query-gpu=utilization.gpu,name", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
        if completed.returncode != 0:
            return None, None
        values: list[float] = []
        names: list[str] = []
        for row in csv.reader(io.StringIO(completed.stdout)):
            if not row:
                continue
            try:
                values.append(float(row[0].strip()))
            except (ValueError, IndexError):
                continue
            if len(row) > 1 and row[1].strip():
                names.append(row[1].strip())
        if not values:
            return None, None
        return round(min(100.0, max(values)), 1), ", ".join(names) or "NVIDIA GPU"
    except (OSError, subprocess.SubprocessError):
        return None, None


def _gpu_from_windows_counters() -> tuple[float | None, str | None]:
    if os.name != "nt":
        return None, None
    # GPU Engine utilization is exposed per engine. Summing engines belonging
    # to the same LUID gives a useful adapter-level estimate, capped at 100%.
    command = (
        "Get-Counter -Counter '\\GPU Engine(*)\\Utilization Percentage' "
        "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty CounterSamples | "
        "ForEach-Object { '{0}|{1}' -f $_.InstanceName,$_.CookedValue }"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if completed.returncode != 0:
            return None, None
        totals: dict[str, float] = {}
        for line in completed.stdout.splitlines():
            instance, sep, raw_value = line.rpartition("|")
            if not sep:
                continue
            try:
                value = max(0.0, float(raw_value.strip()))
            except ValueError:
                continue
            luid = "unknown"
            marker = instance.lower().find("luid_")
            if marker >= 0:
                luid = instance[marker:].split("_engtype", 1)[0]
            totals[luid] = totals.get(luid, 0.0) + value
        if not totals:
            return None, None
        return round(min(100.0, max(totals.values())), 1), "Windows GPU Engine"
    except (OSError, subprocess.SubprocessError):
        return None, None


def gpu_utilization_percent() -> tuple[float | None, str | None]:
    global _gpu_cache
    now = time.monotonic()
    if _gpu_cache and now - _gpu_cache[0] < _GPU_CACHE_SECONDS:
        return _gpu_cache[1], _gpu_cache[2]
    value, name = _gpu_from_nvidia_smi()
    if value is None:
        value, name = _gpu_from_windows_counters()
    _gpu_cache = (now, value, name)
    return value, name


def snapshot() -> dict[str, Any]:
    """Return a JSON-safe point-in-time resource snapshot."""
    cpu = round(psutil.cpu_percent(interval=None), 1)
    memory = psutil.virtual_memory()
    gpu, gpu_name = gpu_utilization_percent()
    return {
        "timestamp": time.time(),
        "cpu_percent": cpu,
        "ram_percent": round(memory.percent, 1),
        "ram_used_bytes": int(memory.used),
        "ram_total_bytes": int(memory.total),
        "gpu_percent": gpu,
        "gpu_name": gpu_name,
        "gpu_available": gpu is not None,
    }
