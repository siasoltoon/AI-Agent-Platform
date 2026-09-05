"""Task API backed by the canonical Task Contract v1 and durable lifecycle store."""

from __future__ import annotations

import logging
import os
import time
import uuid

from fastapi import APIRouter, HTTPException

from agent_core.mission_memory import MissionMemoryStore
from agent_core.mission_service import MissionService
from agent_core.runtime import AgentRuntime
from backend.storage.mission_store import SQLiteMissionStore
from backend.storage.task_store import TaskQueueCapacityError, TaskStore
from config.production_config import CONFIG
from task_engine.contracts import TaskRequest, TaskResponse, TaskStatus
from task_engine.registry import CommandRegistry
from task_engine.router import TaskRouter

logger = logging.getLogger("ai_agent_backend.tasks")

router = APIRouter(prefix="/tasks", tags=["Tasks"])
runtime = AgentRuntime()
command_registry = CommandRegistry()
task_router = TaskRouter(command_registry)
TASK_STORE = TaskStore(os.getenv("TASK_DB_PATH", "data/tasks.db"))
MISSION_STORE = SQLiteMissionStore(os.getenv("TASK_DB_PATH", "data/tasks.db"))
TASK_RUNNER = None
mission_service = MissionService(runtime=runtime, memory_store=MissionMemoryStore(MISSION_STORE))


def _execute_agent_task(task: TaskRequest, *, task_id: str) -> dict:
    return runtime.execute(prompt=task.prompt, model=task.model, task_id=task_id, timeout_seconds=task.timeout_seconds, metadata=task.metadata)


def _execute_mission_task(task: TaskRequest, *, task_id: str) -> dict:
    """Dispatch explicitly requested professional missions through the real orchestrator."""
    return mission_service.execute(
        task.prompt,
        task_id=task_id,
        model=task.model,
        timeout_seconds=task.timeout_seconds,
        metadata=task.metadata,
    )


command_registry.register("agent.execute", _execute_agent_task)
command_registry.register("mission.execute", _execute_mission_task)


async def _create_task(task: TaskRequest) -> TaskResponse:
    task_id = task.task_id or str(uuid.uuid4())
    if TASK_STORE.get(task_id) is not None:
        raise HTTPException(status_code=409, detail="Task ID already exists.")

    try:
        command = task_router.command_for(task)
        command_registry.resolve(command)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"task_id": task_id, "message": "Invalid task command.", "error": str(exc)}) from exc

    now = time.time()
    record = {
        "id": task_id,
        "prompt": task.prompt,
        "model": task.model,
        "status": TaskStatus.QUEUED.value,
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "metadata": {**task.metadata, "prompt_length": len(task.prompt), "command": command, "timeout_seconds": task.timeout_seconds, "queue_limit": CONFIG.max_queued_tasks},
    }
    try:
        TASK_STORE.create(record, max_queued_tasks=CONFIG.max_queued_tasks)
    except TaskQueueCapacityError as exc:
        raise HTTPException(status_code=429, detail={"task_id": task_id, "message": "Task queue capacity reached.", "max_queued_tasks": CONFIG.max_queued_tasks}) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Task persistence is unavailable.") from exc
    return TaskResponse(**record)


@router.post("/", response_model=TaskResponse, status_code=202)
async def create_task(task: TaskRequest) -> TaskResponse:
    return await _create_task(task)


@router.post("/create", response_model=TaskResponse, status_code=202, include_in_schema=False)
async def create_task_legacy(task: TaskRequest) -> TaskResponse:
    return await _create_task(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    task = TASK_STORE.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return TaskResponse(**task)


@router.get("/{task_id}/events")
async def get_task_events(task_id: str) -> dict:
    if TASK_STORE.get(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"task_id": task_id, "events": TASK_STORE.events(task_id)}


@router.get("/{task_id}/mission")
async def get_mission_audit(task_id: str, event_limit: int = 100) -> dict:
    """Expose the durable professional-mission state and bounded lifecycle event history."""
    try:
        snapshot = mission_service.inspect(task_id, event_limit=event_limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Mission not found.")
    return snapshot


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: str) -> TaskResponse:
    logger.warning("[CANCEL] backend endpoint entered task_id=%s", task_id)
    try:
        task = TASK_STORE.cancel(task_id)
    except KeyError as exc:
        logger.warning("[CANCEL] backend task not found task_id=%s", task_id)
        raise HTTPException(status_code=404, detail="Task not found.") from exc

    command = str(task.get("metadata", {}).get("command", ""))
    if command == "mission.execute":
        logger.warning("[CANCEL] routing professional mission through MissionService task_id=%s", task_id)
        try:
            mission_result = mission_service.cancel(task_id, objective=task.get("prompt"))
            logger.warning("[CANCEL] mission orchestrator cancellation finished task_id=%s result=%s", task_id, mission_result)
        except ValueError as exc:
            logger.warning("[CANCEL] mission memory cancellation could not be persisted task_id=%s error=%s", task_id, exc)

    logger.warning("[CANCEL] backend store cancelled task_id=%s status=%s", task_id, task.get("status"))
    logger.warning("[CANCEL] backend propagating to worker task_id=%s worker_base_url=%s", task_id, runtime.worker_client.base_url)
    worker_result = runtime.worker_client.cancel_task(task_id)
    logger.warning("[CANCEL] backend worker propagation finished task_id=%s result=%s", task_id, worker_result)
    return TaskResponse(**task)


@router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_failed_task(task_id: str) -> TaskResponse:
    """Explicitly requeue a failed task; generic lifecycle updates remain strict."""
    try:
        task = TASK_STORE.retry_failed(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"task_id": task_id, "message": str(exc)}) from exc
    return TaskResponse(**task)


@router.post("/{task_id}/resume", response_model=TaskResponse)
async def resume_completed_task(task_id: str) -> TaskResponse:
    """Explicitly resume a completed task with the same durable task identity."""
    try:
        task = TASK_STORE.resume_completed(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"task_id": task_id, "message": str(exc)}) from exc
    return TaskResponse(**task)


@router.get("", response_model=dict)
async def list_tasks(limit: int = 100, status: str | None = None) -> dict:
    if status is not None and status.strip().lower() not in {item.value for item in TaskStatus}:
        raise HTTPException(status_code=400, detail="Invalid task status filter.")
    return {"tasks": TASK_STORE.list(limit=limit, status=status)}
