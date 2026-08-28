from fastapi import APIRouter

router = APIRouter(prefix="/agents")


@router.get("/")
def list_agents():
    return {"agents": []}


@router.get("/{agent_id}")
def get_agent(agent_id: str):
    return {"agent_id": agent_id, "status": "idle"}
