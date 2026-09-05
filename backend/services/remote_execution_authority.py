"""HTTP-backed execution and side-effect authority for remote workers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import requests


class RemoteExecutionAuthority:
    """Expose the controller's authoritative execution ledger to remote workers."""

    def __init__(self, base_url: str, *, token: str | None = None, timeout: float = 5.0) -> None:
        self.base_url = str(base_url).rstrip("/")
        self.token = token or None
        self.timeout = float(timeout)
        self.path = self.base_url

    @staticmethod
    def request_hash(tool_name: str, arguments: Any) -> str:
        payload = json.dumps({"tool": str(tool_name), "arguments": arguments}, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(f"{self.base_url}{path}", json=payload, headers=self._headers(), timeout=self.timeout)
        try:
            body = response.json()
        except ValueError:
            body = {"error": response.text.strip() or response.reason}
        if not response.ok:
            raise RuntimeError(f"Remote execution authority HTTP {response.status_code}: {body.get('error') or body.get('detail') or body}")
        return body if isinstance(body, dict) else {}

    def fence_check(self, task_id: str, execution_id: str, fencing_token: int) -> bool:
        result = self._post("/internal/execution/fence", {"task_id": task_id, "execution_id": execution_id, "fencing_token": int(fencing_token)})
        return bool(result.get("current"))

    def get(self, idempotency_key: str) -> dict[str, Any] | None:
        result = self._post("/internal/execution/side-effects/get", {"idempotency_key": idempotency_key})
        record = result.get("record")
        return record if isinstance(record, dict) else None

    def begin(self, *, idempotency_key: str, task_id: str, execution_id: str, fencing_token: int, tool_name: str, request_hash: str, now: float | None = None) -> dict[str, Any]:
        payload = {"idempotency_key": idempotency_key, "task_id": task_id, "execution_id": execution_id, "fencing_token": int(fencing_token), "tool_name": tool_name, "request_hash": request_hash}
        if now is not None:
            payload["now"] = float(now)
        return self._post("/internal/execution/side-effects/begin", payload).get("record", {})

    def commit(self, idempotency_key: str, *, result: Any = None, now: float | None = None) -> bool:
        payload = {"idempotency_key": idempotency_key, "result": result}
        if now is not None:
            payload["now"] = float(now)
        return bool(self._post("/internal/execution/side-effects/commit", payload).get("committed"))

    def transition(self, idempotency_key: str, state: str, *, error: str | None = None, now: float | None = None) -> bool:
        payload = {"idempotency_key": idempotency_key, "state": state, "error": error}
        if now is not None:
            payload["now"] = float(now)
        return bool(self._post("/internal/execution/side-effects/transition", payload).get("transitioned"))
