"""Worker monitoring API backed by the configured execution worker."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.services.worker_client import WorkerClient
from config.worker_config import WORKER_HOST, WORKER_PORT

router = APIRouter(prefix="/workers", tags=["Workers"])
worker_client = WorkerClient(host=WORKER_HOST, port=WORKER_PORT)


def _worker_record() -> dict[str, Any]:
    try:
        health = worker_client.health_check()
    except Exception as exc:
        return {
            "worker_id": f"{WORKER_HOST}:{WORKER_PORT}",
            "host": WORKER_HOST,
            "port": WORKER_PORT,
            "status": "offline",
            "health": None,
            "resources": None,
            "error": str(exc),
        }

    resources = health.get("resources") if isinstance(health.get("resources"), dict) else None
    worker_status = str(health.get("worker_status") or "unknown").lower()
    return {
        "worker_id": str(health.get("worker_id") or f"{WORKER_HOST}:{WORKER_PORT}"),
        "host": WORKER_HOST,
        "port": WORKER_PORT,
        "status": "online",
        "worker_status": worker_status,
        "health": health,
        "resources": resources,
        "error": None,
    }


@router.get("/")
def list_workers():
    """Return the configured execution worker with live resource telemetry."""
    return {"workers": [_worker_record()]}


@router.get("/{worker_id}")
def get_worker(worker_id: str):
    """Return the configured worker when the requested id matches it."""
    record = _worker_record()
    if worker_id not in {record["worker_id"], f"{WORKER_HOST}:{WORKER_PORT}"}:
        return {"worker_id": worker_id, "status": "unknown"}
    return record
