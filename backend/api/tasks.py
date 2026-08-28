from fastapi import APIRouter

router = APIRouter(prefix="/tasks")


@router.get("/")
def list_tasks():
    return {"tasks": []}


@router.post("/")
def create_task(task: dict):
    return {"status": "queued", "task": task}


@router.get("/{task_id}")
def get_task(task_id: str):
    return {"task_id": task_id, "status": "unknown"}
