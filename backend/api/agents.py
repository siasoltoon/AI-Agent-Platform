"""
Agent API

Handles:
- Agent status
- Agent execution
- Agent communication
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import uuid
import time


router = APIRouter(
    prefix="/agents",
    tags=["Agents"]
)


AGENT_STATE = {

    "status": "idle",

    "current_task": None,

    "last_result": None,

    "started_at": None

}



class AgentRunRequest(BaseModel):

    prompt: str

    model: str = "qwen2.5-coder"



@router.get("/status")
async def agent_status():

    return AGENT_STATE



@router.post("/run")
async def run_agent(
    request: AgentRunRequest
):

    task_id = str(uuid.uuid4())


    AGENT_STATE["status"] = "running"

    AGENT_STATE["current_task"] = {

        "id": task_id,

        "prompt": request.prompt,

        "model": request.model

    }

    AGENT_STATE["started_at"] = time.time()



    # مرحله بعد:
    #
    # اتصال واقعی:
    #
    # agent_manager.execute()
    #
    # Ollama call
    #



    AGENT_STATE["status"] = "completed"

    AGENT_STATE["last_result"] = {

        "task_id": task_id,

        "message": "Agent execution pipeline ready"

    }



    return {

        "task_id": task_id,

        "status": "completed",

        "result": AGENT_STATE["last_result"]

    }
