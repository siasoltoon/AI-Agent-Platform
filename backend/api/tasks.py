"""
Task API

Handles:
- Creating tasks
- Checking task status
- Sending tasks to Agent Runtime
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid
import time


router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"]
)


# Temporary in-memory storage
# Later replaced by database
TASK_STORE = {}


class TaskCreate(BaseModel):
    prompt: str
    model: Optional[str] = "qwen2.5-coder"


class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str



@router.post(
    "/create",
    response_model=TaskResponse
)
async def create_task(
    task: TaskCreate
):

    task_id = str(uuid.uuid4())


    TASK_STORE[task_id] = {

        "id": task_id,

        "prompt": task.prompt,

        "model": task.model,

        "status": "queued",

        "created_at": time.time(),

        "result": None
    }


    # Later:
    # send task to Agent Manager
    #
    # agent_manager.submit(task_id)


    return TaskResponse(

        task_id=task_id,

        status="queued",

        message="Task created successfully"

    )




@router.get(
    "/{task_id}"
)
async def get_task(
    task_id: str
):

    task = TASK_STORE.get(task_id)


    if not task:

        raise HTTPException(

            status_code=404,

            detail="Task not found"

        )


    return task




@router.get("")
async def list_tasks():

    return {

        "tasks": list(
            TASK_STORE.values()
        )

    }
