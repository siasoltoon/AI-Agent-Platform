"""Task API backed by the canonical Task Contract v1."""

from __future__ import annotations

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
TASK_STORE = TaskStore()


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


@router.post("/create", response_model=TaskResponse)
async def create_task(task: TaskRequest) -> TaskResponse:
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
        },
    }
    try:
        TASK_STORE.create(record)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Task persistence is unavailable.") from exc

    TASK_STORE.update(task_id, status=TaskStatus.RUNNING.value, started_at=time.time())

    try:
        result = task_router.route(task, task_id=task_id)
        metadata = {"execution_mode": result.get("execution_mode", "agentic")}
        nested = result.get("result")
        if isinstance(nested, dict):
            metadata.update(
                {
                    "steps": nested.get("steps", 1),
                    "orchestration_mode": nested.get("mode", "agentic"),
                }
            )
        task_record = TASK_STORE.update(
            task_id,
            status=TaskStatus.COMPLETED.value,
            completed_at=time.time(),
            result=result,
            metadata={**TASK_STORE.get(task_id)["metadata"], **metadata},
        )
        return TaskResponse(**task_record)
    except TimeoutError as exc:
        error = str(exc) or "Task execution timed out."
        task_record = TASK_STORE.update(
            task_id,
            status=TaskStatus.FAILED.value,
            completed_at=time.time(),
            error=error,
        )
        raise HTTPException(
            status_code=504,
            detail={"task_id": task_id, "message": "Task execution timed out.", "error": error},
        ) from exc
    except Exception as exc:
        task_record = TASK_STORE.update(
            task_id,
            status=TaskStatus.FAILED.value,
            completed_at=time.time(),
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={"task_id": task_id, "message": "Task execution failed.", "error": str(exc)},
        ) from exc


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    task = TASK_STORE.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return TaskResponse(**task)


@router.get("", response_model=dict)
async def list_tasks() -> dict:
    return {"tasks": TASK_STORE.list()}
