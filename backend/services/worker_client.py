"""HTTP client for the AI Agent Platform execution worker.

The client preserves structured worker failures and distinguishes definitive
request failures from ambiguous execution outcomes. Ambiguous outcomes must
be reconciled with the worker using the same task id before a caller retries a
side-effectful task.
"""

from __future__ import annotations

from typing import Any

import requests


class WorkerExecutionError(RuntimeError):
    """Structured worker failure with retry and execution-ambiguity metadata."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        ambiguous: bool,
        status_code: int | None = None,
        task_id: str | None = None,
    ) -> None:
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

        # A 4xx response is a definitive application/request outcome. A 5xx
        # response is ambiguous: the worker may have completed a side effect
        # before the HTTP response failed. Do not blindly replay the request.
        ambiguous = response.status_code >= 500
        retryable = response.status_code in {408, 429} or 500 <= response.status_code < 600
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
            raise WorkerExecutionError(
                "Worker health request timed out.", retryable=True, ambiguous=False
            ) from exc
        except requests.RequestException as exc:
            raise WorkerExecutionError(
                f"Worker health request failed: {exc}", retryable=True, ambiguous=False
            ) from exc
        self._raise_for_worker_error(response)
        return response.json()

    def execute_task(
        self,
        task: dict[str, Any],
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Execute one worker request without unsafe blind retries.

        Network timeouts/disconnects and worker 5xx responses are marked
        ambiguous because the worker may have executed the side effect before
        the client lost the response. Callers should reconcile using the same
        task id rather than immediately issuing a new side-effectful request.
        """
        effective_timeout = timeout or int(task.get("timeout", 300))
        task_id = self._task_id(task)
        try:
            response = requests.post(
                f"{self.base_url}/execute",
                json=task,
                timeout=effective_timeout,
            )
        except requests.Timeout as exc:
            raise WorkerExecutionError(
                f"Worker request timed out after {effective_timeout} seconds.",
                retryable=True,
                ambiguous=True,
                task_id=task_id,
            ) from exc
        except requests.RequestException as exc:
            raise WorkerExecutionError(
                f"Worker request failed: {exc}",
                retryable=True,
                ambiguous=True,
                task_id=task_id,
            ) from exc

        self._raise_for_worker_error(response, task_id=task_id)
        try:
            payload = response.json()
        except ValueError as exc:
            raise WorkerExecutionError(
                "Worker returned a non-JSON response.",
                retryable=True,
                ambiguous=True,
                status_code=response.status_code,
                task_id=task_id,
            ) from exc
        if not isinstance(payload, dict):
            raise WorkerExecutionError(
                "Worker returned an invalid JSON response object.",
                retryable=True,
                ambiguous=True,
                status_code=response.status_code,
                task_id=task_id,
            )
        return payload
