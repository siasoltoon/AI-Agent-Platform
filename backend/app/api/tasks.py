"""Task API foundation."""

from fastapi import APIRouter

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/")
def list_tasks():
    return {"tasks": []}


@router.post("/")
def create_task(payload: dict):
    return {"status": "accepted", "task": payload}
