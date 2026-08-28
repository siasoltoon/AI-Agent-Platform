from fastapi import APIRouter

router = APIRouter(prefix="/workers")


@router.get("/")
def list_workers():
    return {"workers": []}


@router.get("/{worker_id}")
def get_worker(worker_id: str):
    return {"worker_id": worker_id, "status": "offline"}
