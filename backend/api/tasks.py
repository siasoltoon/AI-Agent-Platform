"""Task API backed by the canonical Task Contract v1."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException

from agent_core.runtime import AgentRuntime
from task_engine.contracts import TaskRequest, TaskResponse, TaskStatus
from task_engine.registry import CommandRegistry
from task_engine.router import TaskRouter


router = APIRouter(prefix="/tasks", tags=["Tasks"])
runtime = AgentRuntime()
command_registry = CommandRegistry()
task_router = TaskRouter(command_registry)
TASK_STORE: dict[str, dict] = {}


def _execute_agent_task(task: TaskRequest, *, task_id: str) -> dict:
    """Default command handler for the existing Agent Runtime path."""
    return runtime.execute(
        prompt=task.prompt,
        model=task.model,
        task_id=task_id,
        timeout_seconds=task.timeout_seconds,
    )


command_registry.register("agent.execute", _execute_agent_task)


@router.post("/create", response_model=TaskResponse)
async def create_task(task: TaskRequest) -> TaskResponse:
    """Create and execute a task through the command router."""
    task_id = task.task_id or str(uuid.uuid4())
    if task_id in TASK_STORE:
        raise HTTPException(status_code=409, detail="Task ID already exists.")

    try:
        command = task_router.command_for(task)
        command_registry.resolve(command)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "task_id": task_id,
                "message": "Invalid task command.",
                "error": str(exc),
            },
        ) from exc

    now = time.time()
    TASK_STORE[task_id] = {
        "id": task_id,
        "prompt": task.prompt,
        "model": task.model,
        "status": TaskStatus.QUEUED,
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

    TASK_STORE[task_id]["status"] = TaskStatus.RUNNING
    TASK_STORE[task_id]["started_at"] = time.time()

    try:
        result = task_router.route(task, task_id=task_id)

        TASK_STORE[task_id]["status"] = TaskStatus.COMPLETED
        TASK_STORE[task_id]["completed_at"] = time.time()
        TASK_STORE[task_id]["result"] = result
        TASK_STORE[task_id]["metadata"].update({
            "execution_mode": result.get("execution_mode", "single"),
        })

        nested = result.get("result")
        if isinstance(nested, dict):
            TASK_STORE[task_id]["metadata"].update({
                "steps": nested.get("steps", 1),
                "orchestration_mode": nested.get("mode", "single"),
            })

        return TaskResponse(**TASK_STORE[task_id])

    except Exception as exc:
        TASK_STORE[task_id]["status"] = TaskStatus.FAILED
        TASK_STORE[task_id]["completed_at"] = time.time()
        TASK_STORE[task_id]["error"] = str(exc)
        raise HTTPException(
            status_code=502,
            detail={
                "task_id": task_id,
                "message": "Task execution failed.",
                "error": str(exc),
            },
        ) from exc


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    task = TASK_STORE.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return TaskResponse(**task)


@router.get("", response_model=dict)
async def list_tasks() -> dict:
    return {"tasks": list(TASK_STORE.values())}
