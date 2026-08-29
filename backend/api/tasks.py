"""Task API backed by the canonical Task Contract v1."""

from __future__ import annotations

import os
import time
import uuid

from fastapi import APIRouter, HTTPException

from agent_core.runtime import AgentRuntime
from backend.storage.task_store import TaskStore
from task_engine.contracts import TaskRequest, TaskResponse, TaskStatus
from task_engine.registry import CommandRegistry
from task_engine.router import TaskRouter

router = APIRouter(prefix="/tasks", tags=["Tasks"])
runtime = AgentRuntime()
command_registry = CommandRegistry()
task_router = TaskRouter(command_registry)
TASK_STORE = TaskStore(os.getenv("TASK_DB_PATH", "data/tasks.db"))


def _execute_agent_task(task: TaskRequest, *, task_id: str) -> dict:
    """Default command: execute the task on the real agentic worker."""
    return runtime.execute(
        prompt=task.prompt,
        model=task.model,
        task_id=task_id,
        timeout_seconds=task.timeout_seconds,
        metadata=task.metadata,
    )


command_registry.register("agent.execute", _execute_agent_task)


async def _create_task(task: TaskRequest) -> TaskResponse:
    """Persist a task and let the background runner execute it."""
    task_id = task.task_id or str(uuid.uuid4())
    if TASK_STORE.get(task_id) is not None:
        raise HTTPException(status_code=409, detail="Task ID already exists.")

    try:
        command = task_router.command_for(task)
        command_registry.resolve(command)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail={"task_id": task_id, "message": "Invalid task command.", "error": str(exc)},
        ) from exc

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
        "metadata": {
            **task.metadata,
            "prompt_length": len(task.prompt),
            "command": command,
            "timeout_seconds": task.timeout_seconds,
        },
    }
    try:
        TASK_STORE.create(record)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Task persistence is unavailable.") from exc

    return TaskResponse(**record)


# The web dashboard uses POST /tasks/. Keep /tasks/create as a compatibility alias.
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


@router.get("", response_model=dict)
async def list_tasks() -> dict:
    return {"tasks": TASK_STORE.list()}
