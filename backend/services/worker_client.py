"""HTTP client for the AI Agent Platform execution worker.

The client preserves the worker's structured error payload so the controller
and dashboard can report the real execution failure instead of a bare HTTP
status such as ``422 Client Error``.
"""

from __future__ import annotations

from typing import Any

import requests


class WorkerClient:
    def __init__(self, host: str, port: int):
        self.base_url = f"http://{host}:{port}"

    @staticmethod
    def _raise_for_worker_error(response: requests.Response) -> None:
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
        else:
            message = str(detail or response.reason or "Worker request failed")

        raise RuntimeError(f"Worker HTTP {response.status_code}: {message}")

    def health_check(self) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url}/health",
            timeout=10,
        )
        self._raise_for_worker_error(response)
        return response.json()

    def execute_task(
        self,
        task: dict[str, Any],
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Execute one worker request and preserve structured failure details."""
        effective_timeout = timeout or int(task.get("timeout", 300))
        try:
            response = requests.post(
                f"{self.base_url}/execute",
                json=task,
                timeout=effective_timeout,
            )
        except requests.Timeout as exc:
            raise RuntimeError(
                f"Worker request timed out after {effective_timeout} seconds."
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Worker request failed: {exc}") from exc

        self._raise_for_worker_error(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Worker returned a non-JSON response.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Worker returned an invalid JSON response object.")
        return payload
