"""Execution fence shared by agent tools to reject stale workers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.storage.execution_ledger import ExecutionLedger
from backend.storage.side_effect_ledger import SideEffectLedger


class ExecutionFenceError(RuntimeError):
    """Raised when a stale or superseded execution attempts a side effect."""


class ExecutionFence:
    """Validate the current attempt and deduplicate side-effect requests."""

    def __init__(self, *, task_id: str, execution_id: str, fencing_token: int, ledger: ExecutionLedger, side_effects: SideEffectLedger | None = None) -> None:
        self.task_id = str(task_id)
        self.execution_id = str(execution_id)
        self.fencing_token = int(fencing_token)
        self.ledger = ledger
        self.side_effects = side_effects or SideEffectLedger(ledger.path)

    def assert_current(self) -> None:
        if not self.ledger.fence_check(self.task_id, self.execution_id, self.fencing_token):
            raise ExecutionFenceError("Execution fence rejected side effect because this attempt is no longer current.")

    @staticmethod
    def key(tool_name: str, arguments: Any) -> str:
        payload = json.dumps({"tool": str(tool_name), "arguments": arguments}, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def begin_side_effect(self, tool_name: str, arguments: Any) -> tuple[str, dict[str, Any]]:
        self.assert_current()
        key = self.key(tool_name, arguments)
        request_hash = self.side_effects.request_hash(tool_name, arguments)
        record = self.side_effects.begin(
            idempotency_key=key,
            task_id=self.task_id,
            execution_id=self.execution_id,
            fencing_token=self.fencing_token,
            tool_name=str(tool_name),
            request_hash=request_hash,
        )
        if record.get("execution_id") != self.execution_id or int(record.get("fencing_token", -1)) != self.fencing_token:
            if record.get("state") == "committed" and record.get("result_json") is not None:
                return key, record
            raise ExecutionFenceError("Side effect is already owned by another execution and cannot be replayed safely.")
        if record.get("state") == "ambiguous":
            raise ExecutionFenceError("Side effect outcome is ambiguous and must not be replayed automatically.")
        return key, record

    def commit_side_effect(self, key: str, result: Any) -> Any:
        self.assert_current()
        record = self.side_effects.get(key)
        if record and record.get("state") == "committed" and record.get("result_json") is not None:
            return json.loads(record["result_json"])
        if not self.side_effects.commit(key, result=result):
            raise ExecutionFenceError("Execution fence rejected side-effect commit.")
        return result

    def mark_ambiguous(self, key: str, error: str) -> None:
        self.side_effects.transition(key, "ambiguous", error=error)
