"""
Task API

Handles:
- Creating tasks
- Retrieving tasks
- Listing tasks
- Executing tasks through Agent Runtime
"""

import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_core.runtime import AgentRuntime


router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"],
)


runtime = AgentRuntime()


TASK_STORE = {}


class TaskCreate(BaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        description="Task instruction.",
    )

    model: Optional[str] = Field(
        default=None,
        description="Ollama model to use.",
    )


@router.post("/create")
async def create_task(
    task: TaskCreate,
):
    """
    Create and execute a task through the Agent Runtime.
    """

    task_id = str(uuid.uuid4())

    selected_model = task.model

    TASK_STORE[task_id] = {
        "id": task_id,
        "prompt": task.prompt,
        "model": selected_model,
        "status": "queued",
        "created_at": time.time(),
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
    }

    TASK_STORE[task_id]["status"] = "running"
    TASK_STORE[task_id]["started_at"] = time.time()

    try:

        result = runtime.execute(
            prompt=task.prompt,
            model=selected_model,
            task_id=task_id,
        )

        TASK_STORE[task_id]["status"] = "completed"
        TASK_STORE[task_id]["completed_at"] = time.time()
        TASK_STORE[task_id]["result"] = result

        return TASK_STORE[task_id]

    except Exception as exc:

        TASK_STORE[task_id]["status"] = "failed"
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


@router.get("/{task_id}")
async def get_task(
    task_id: str,
):
    """
    Return a task by ID.
    """

    task = TASK_STORE.get(task_id)

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Task not found.",
        )

    return task


@router.get("")
async def list_tasks():
    """
    Return all tasks.
    """

    return {
        "tasks": list(
            TASK_STORE.values()
        )
    }
