"""HTTP client for the AI Agent Platform execution worker."""

from __future__ import annotations

from typing import Any

import requests


class WorkerClient:
    def __init__(self, host: str, port: int):
        self.base_url = f"http://{host}:{port}"

    def health_check(self) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url}/health",
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def execute_task(
        self,
        task: dict[str, Any],
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Execute one worker request using the task's effective timeout."""
        effective_timeout = timeout or int(task.get("timeout", 300))
        response = requests.post(
            f"{self.base_url}/execute",
            json=task,
            timeout=effective_timeout,
        )
        response.raise_for_status()
        return response.json()
