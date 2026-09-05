"""Remote-worker entrypoint that keeps execution authority on the controller."""

from __future__ import annotations

import worker_system.worker as base_worker

from backend.services.remote_execution_authority import RemoteExecutionAuthority
from config.worker_config import EXECUTION_AUTHORITY_TIMEOUT, EXECUTION_AUTHORITY_TOKEN, EXECUTION_AUTHORITY_URL


if not EXECUTION_AUTHORITY_URL:
    raise RuntimeError("EXECUTION_AUTHORITY_URL is required for the remote worker entrypoint.")


class RemoteExecutionLedger:
    """ExecutionLedger-compatible fence facade backed by the controller."""

    def __init__(self, _path: str = "") -> None:
        self.authority = RemoteExecutionAuthority(
            EXECUTION_AUTHORITY_URL,
            token=EXECUTION_AUTHORITY_TOKEN,
            timeout=EXECUTION_AUTHORITY_TIMEOUT,
        )
        self.path = EXECUTION_AUTHORITY_URL

    def fence_check(self, task_id: str, execution_id: str, fencing_token: int) -> bool:
        return self.authority.fence_check(task_id, execution_id, fencing_token)


class RemoteSideEffectLedger:
    """SideEffectLedger-compatible facade backed by the controller."""

    def __init__(self, _path: str = "") -> None:
        self.authority = RemoteExecutionAuthority(
            EXECUTION_AUTHORITY_URL,
            token=EXECUTION_AUTHORITY_TOKEN,
            timeout=EXECUTION_AUTHORITY_TIMEOUT,
        )
        self.path = EXECUTION_AUTHORITY_URL

    request_hash = staticmethod(RemoteExecutionAuthority.request_hash)

    def get(self, idempotency_key: str):
        return self.authority.get(idempotency_key)

    def begin(self, **kwargs):
        return self.authority.begin(**kwargs)

    def commit(self, idempotency_key: str, *, result=None, now=None):
        record = self.get(idempotency_key)
        if record is None:
            return False
        return self.authority.commit(
            idempotency_key,
            result=result,
            now=now,
            execution_id=record.get("execution_id"),
            fencing_token=int(record.get("fencing_token", -1)),
        )

    def transition(self, idempotency_key: str, state: str, *, error=None, now=None, execution_id=None, fencing_token=None):
        return self.authority.transition(
            idempotency_key,
            state,
            error=error,
            now=now,
            execution_id=execution_id,
            fencing_token=fencing_token,
        )


# The existing Worker implementation resolves these names when execute() runs.
# Rebinding them here preserves all worker behavior while moving authoritative
# fencing and durable side-effect state to the controller process/database.
base_worker.ExecutionLedger = RemoteExecutionLedger
base_worker.SideEffectLedger = RemoteSideEffectLedger

app = base_worker.app
worker = base_worker.worker
