from fastapi import APIRouter

router = APIRouter(prefix="/workers", tags=["Workers"])


@router.get("/")
def list_workers():
    """Return registered workers from the current worker registry contract."""
    return {"workers": []}


@router.get("/{worker_id}")
def get_worker(worker_id: str):
    """Return a worker record when the worker registry exposes one."""
    return {"worker_id": worker_id, "status": "offline"}
