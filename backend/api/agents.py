"""
Agent API

HTTP API for interacting with the Agent Runtime.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_core.runtime import AgentRuntime


router = APIRouter(
    prefix="/agents",
    tags=["Agents"],
)


runtime = AgentRuntime()


class AgentRunRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        description="Task instruction for the agent.",
    )

    model: Optional[str] = Field(
        default=None,
        description="Ollama model to use.",
    )

    task_id: Optional[str] = Field(
        default=None,
        description="Optional existing task ID.",
    )


@router.get("/status")
async def agent_status():
    """
    Return the current worker connectivity status.
    """

    try:
        worker_status = runtime.health_check()

        return {
            "status": "ready",
            "worker": worker_status,
        }

    except Exception as exc:
        return {
            "status": "offline",
            "worker": None,
            "error": str(exc),
        }


@router.post("/run")
async def run_agent(
    request: AgentRunRequest,
):
    """
    Send a task to the Agent Runtime.
    """

    try:
        result = runtime.execute(
            prompt=request.prompt,
            model=request.model,
            task_id=request.task_id,
        )

        return {
            "status": "completed",
            "result": result,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Agent Worker is unavailable or execution failed.",
                "error": str(exc),
            },
        ) from exc
