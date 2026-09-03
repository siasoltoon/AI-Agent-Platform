"""HTTP client for the AI Agent Platform execution worker."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger("ai_agent_backend.worker_client")


class WorkerExecutionError(RuntimeError):
    """Structured worker failure with retry and execution-ambiguity metadata."""

    def __init__(self, message: str, *, retryable: bool, ambiguous: bool, status_code: int | None = None, task_id: str | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.ambiguous = ambiguous
        self.status_code = status_code
        self.task_id = task_id


class WorkerClient:
    def __init__(self, host: str, port: int):
        self.base_url = f"http://{host}:{port}"

    @staticmethod
    def _task_id(task: dict[str, Any]) -> str | None:
        value = task.get("task_id")
        return str(value).strip() or None if value is not None else None

    @classmethod
    def _raise_for_worker_error(cls, response: requests.Response, task_id: str | None = None) -> None:
        if response.ok:
            return
        detail: Any = None
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = payload.get("detail", payload)
            else:
                detail = payload
        except ValueError:
            detail = response.text.strip() or None

        if isinstance(detail, dict):
            message = detail.get("error") or detail.get("message") or str(detail)
            error_type = detail.get("error_type")
            if error_type:
                message = f"{error_type}: {message}"
            task_id = task_id or detail.get("task_id")
        else:
            message = str(detail or response.reason or "Worker request failed")

        lower = str(message).lower()
        execution_timeout = "timed out" in lower or "timeout" in lower
        execution_cancelled = "cancelled" in lower or "canceled" in lower
        ambiguous = response.status_code >= 500 or execution_timeout or execution_cancelled
        retryable = response.status_code in {408, 429} or 500 <= response.status_code < 600 or execution_timeout or execution_cancelled
        if execution_timeout:
            message = f"Worker request timed out: {message}"
        elif execution_cancelled:
            message = f"Worker request cancelled: {message}"
        raise WorkerExecutionError(
            f"Worker HTTP {response.status_code}: {message}",
            retryable=retryable,
            ambiguous=ambiguous,
            status_code=response.status_code,
            task_id=str(task_id).strip() if task_id else None,
        )

    def health_check(self) -> dict[str, Any]:
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
        except requests.Timeout as exc:
            raise WorkerExecutionError("Worker health request timed out.", retryable=True, ambiguous=False) from exc
        except requests.RequestException as exc:
            raise WorkerExecutionError(f"Worker health request failed: {exc}", retryable=True, ambiguous=False) from exc
        self._raise_for_worker_error(response)
        return response.json()

    def cancel_task(self, task_id: str, *, timeout: float = 5.0) -> dict[str, Any] | None:
        """Ask the worker to cooperatively cancel an in-flight task."""
        task_id = str(task_id or "").strip()
        logger.warning("[CANCEL->WORKER] begin task_id=%s url=%s/cancel/%s timeout=%s", task_id or "<empty>", self.base_url, task_id or "<empty>", timeout)
        if not task_id:
            logger.warning("[CANCEL->WORKER] rejected empty task_id")
            return None
        try:
            response = requests.post(f"{self.base_url}/cancel/{task_id}", timeout=timeout)
            logger.warning("[CANCEL->WORKER] response task_id=%s status=%s body=%s", task_id, response.status_code, response.text[:500])
            self._raise_for_worker_error(response, task_id=task_id)
            payload = response.json()
            logger.warning("[CANCEL->WORKER] success task_id=%s payload=%s", task_id, payload)
            return payload if isinstance(payload, dict) else None
        except requests.RequestException as exc:
            logger.error("[CANCEL->WORKER] request_exception task_id=%s error_type=%s error=%s", task_id, type(exc).__name__, exc)
            return None

    def execute_task(self, task: dict[str, Any], timeout: int | None = None) -> dict[str, Any]:
        """Execute one worker request without unsafe blind retries."""
        effective_timeout = timeout or int(task.get("timeout", 300))
        task_id = self._task_id(task)
        try:
            response = requests.post(f"{self.base_url}/execute", json=task, timeout=effective_timeout)
        except requests.Timeout as exc:
            if task_id:
                self.cancel_task(task_id)
            raise WorkerExecutionError(
                f"Worker request timed out after {effective_timeout} seconds.", retryable=True, ambiguous=True, task_id=task_id
            ) from exc
        except requests.RequestException as exc:
            if task_id:
                self.cancel_task(task_id)
            raise WorkerExecutionError(
                f"Worker request failed: {exc}", retryable=True, ambiguous=True, task_id=task_id
            ) from exc

        self._raise_for_worker_error(response, task_id=task_id)
        try:
            payload = response.json()
        except ValueError as exc:
            if task_id:
                self.cancel_task(task_id)
            raise WorkerExecutionError(
                "Worker returned a non-JSON response.", retryable=True, ambiguous=True, status_code=response.status_code, task_id=task_id
            ) from exc
        if not isinstance(payload, dict):
            raise WorkerExecutionError(
                "Worker returned an invalid JSON response object.", retryable=True, ambiguous=True, status_code=response.status_code, task_id=task_id
            )
        return payload
