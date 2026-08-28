from fastapi import APIRouter

router = APIRouter(prefix="/tasks")

@router.get("/")
def list_tasks():
    return {"tasks": []}
