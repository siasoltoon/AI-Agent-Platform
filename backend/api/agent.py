from fastapi import APIRouter

router = APIRouter(prefix="/agent")

@router.get("/status")
def agent_status():
    return {"status": "idle"}
