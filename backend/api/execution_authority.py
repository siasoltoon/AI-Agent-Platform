"""Internal controller endpoints used by remote execution workers."""

from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.api import tasks
from backend.storage.side_effect_ledger import SideEffectLedger

router = APIRouter(prefix="/internal/execution", tags=["Internal Execution"])
side_effects = SideEffectLedger(tasks.TASK_STORE.path)


def _authorize(authorization: str | None) -> None:
    expected = os.getenv("EXECUTION_AUTHORITY_TOKEN")
    if expected and not hmac.compare_digest(str(authorization or ""), f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="Execution authority authentication failed.")


class FenceRequest(BaseModel):
    task_id: str
    execution_id: str
    fencing_token: int


class SideEffectBeginRequest(FenceRequest):
    idempotency_key: str
    tool_name: str
    request_hash: str
    now: float | None = None


class SideEffectKeyRequest(BaseModel):
    idempotency_key: str


class SideEffectCommitRequest(SideEffectKeyRequest):
    result: Any = None
    execution_id: str
    fencing_token: int
    now: float | None = None


class SideEffectTransitionRequest(SideEffectKeyRequest):
    state: str
    execution_id: str
    fencing_token: int
    error: str | None = None
    now: float | None = None


@router.post("/fence")
def fence(request: FenceRequest, authorization: str | None = Header(default=None)) -> dict[str, bool]:
    _authorize(authorization)
    return {"current": tasks.EXECUTION_LEDGER.fence_check(request.task_id, request.execution_id, request.fencing_token)}


@router.post("/side-effects/get")
def side_effect_get(request: SideEffectKeyRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(authorization)
    return {"record": side_effects.get(request.idempotency_key)}


@router.post("/side-effects/begin")
def side_effect_begin(request: SideEffectBeginRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(authorization)
    if not tasks.EXECUTION_LEDGER.fence_check(request.task_id, request.execution_id, request.fencing_token):
        raise HTTPException(status_code=409, detail="Execution is no longer current.")
    record = side_effects.begin(
        idempotency_key=request.idempotency_key,
        task_id=request.task_id,
        execution_id=request.execution_id,
        fencing_token=request.fencing_token,
        tool_name=request.tool_name,
        request_hash=request.request_hash,
        now=request.now,
    )
    return {"record": record}


@router.post("/side-effects/commit")
def side_effect_commit(request: SideEffectCommitRequest, authorization: str | None = Header(default=None)) -> dict[str, bool]:
    _authorize(authorization)
    record = side_effects.get(request.idempotency_key)
    if record is None or record.get("execution_id") != request.execution_id or int(record.get("fencing_token", -1)) != request.fencing_token:
        raise HTTPException(status_code=409, detail="Side effect ownership changed.")
    if not tasks.EXECUTION_LEDGER.fence_check(str(record["task_id"]), request.execution_id, request.fencing_token):
        raise HTTPException(status_code=409, detail="Execution is no longer current.")
    return {"committed": side_effects.commit(request.idempotency_key, result=request.result, now=request.now)}


@router.post("/side-effects/transition")
def side_effect_transition(request: SideEffectTransitionRequest, authorization: str | None = Header(default=None)) -> dict[str, bool]:
    _authorize(authorization)
    record = side_effects.get(request.idempotency_key)
    if record is None or record.get("execution_id") != request.execution_id or int(record.get("fencing_token", -1)) != request.fencing_token:
        raise HTTPException(status_code=409, detail="Side effect ownership changed.")
    return {"transitioned": side_effects.transition(request.idempotency_key, request.state, error=request.error, now=request.now)}
