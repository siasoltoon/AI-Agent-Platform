"""Read-only control-plane aggregates for the production dashboard."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

from backend.api import agents, tasks, workers
from backend.storage.execution_ledger import ExecutionLedger
from backend.storage.side_effect_ledger import SideEffectLedger

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _safe_agent_status() -> dict[str, Any]:
    try: return agents.runtime.health_check()
    except Exception as exc: return {"status": "offline", "error": str(exc)}


def _safe_workers() -> dict[str, Any]:
    try: return workers.list_workers()
    except Exception as exc: return {"workers": [], "error": str(exc)}


def _safe_execution_state() -> dict[str, Any]:
    path = getattr(tasks.TASK_STORE, "path", "data/tasks.db")
    try:
        ledger = ExecutionLedger(path); effects = SideEffectLedger(path)
        current = ledger.current if hasattr(ledger, "current") else None
        return {"status": "ok", "side_effects": effects.summary(limit=20)}
    except Exception as exc:
        return {"status": "offline", "error": str(exc)}


@router.get("/summary")
def dashboard_summary() -> dict[str, Any]:
    """Return authoritative, bounded dashboard state without synthetic metrics."""
    summary = tasks.TASK_STORE.summary(recent_limit=20) if hasattr(tasks.TASK_STORE, "summary") else None
    if summary is None:
        task_rows = tasks.TASK_STORE.list(limit=500)
        counts = {"total": len(task_rows), "queued": 0, "running": 0, "completed": 0, "failed": 0, "cancelled": 0}
        for row in task_rows:
            status = str(row.get("status", "")).lower()
            if status in counts and status != "total": counts[status] += 1
        summary = {"counts": counts, "average_execution_seconds": None, "event_count": None, "recent_events": []}
    live = {"status": "ok", "service": "AI-Agent-Platform"}
    try: ready = tasks.TASK_STORE.ping()
    except Exception as exc: ready = False; ready_error = str(exc)
    else: ready_error = None
    agent = _safe_agent_status(); worker_data = _safe_workers(); execution = _safe_execution_state()
    return {"generated_at": time.time(), "system": {"live": live, "ready": {"status": "ready" if ready else "not_ready", "error": ready_error}}, "tasks": summary, "agent": agent, "workers": worker_data, "execution": execution}


@router.get("/diagnostics")
def dashboard_diagnostics() -> dict[str, Any]:
    """Expose explicit backend diagnostics; never report an unavailable domain as healthy."""
    checks: list[dict[str, Any]] = []
    try: tasks.TASK_STORE.ping()
    except Exception as exc: checks.append({"name": "Task Store", "status": "fail", "detail": str(exc)})
    else: checks.append({"name": "Task Store", "status": "pass", "detail": "SQLite reachable"})
    try: agent = agents.runtime.health_check()
    except Exception as exc: checks.append({"name": "Agent Worker", "status": "fail", "detail": str(exc)})
    else: checks.append({"name": "Agent Worker", "status": "pass", "detail": agent})
    worker_data = _safe_workers()
    if worker_data.get("error"): checks.append({"name": "Worker Registry", "status": "fail", "detail": worker_data["error"]})
    else: checks.append({"name": "Worker Registry", "status": "pass", "detail": f"{len(worker_data.get('workers', []))} registered worker(s)"})
    execution = _safe_execution_state()
    checks.append({"name": "Execution Fence Ledger", "status": "pass" if execution.get("status") == "ok" else "fail", "detail": execution})
    return {"generated_at": time.time(), "checks": checks}
