"""Worker API foundation."""

from fastapi import APIRouter

router = APIRouter(prefix="/workers", tags=["workers"])


@router.get("/")
def list_workers():
    return {"workers": []}
