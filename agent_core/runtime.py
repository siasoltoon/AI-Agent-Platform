"""
Agent Runtime

Coordinates task execution between the Agent Core,
Task Engine and Worker layer.
"""

from __future__ import annotations

from typing import Any

from backend.services.worker_client import WorkerClient
from config.worker_config import (
    DEFAULT_MODEL,
    WORKER_HOST,
    WORKER_PORT,
    WORKER_TIMEOUT,
)


class AgentRuntime:
    def __init__(self, worker_client: WorkerClient | None = None):
        self.worker_client = worker_client or WorkerClient(
            host=WORKER_HOST,
            port=WORKER_PORT,
        )
        self.timeout = WORKER_TIMEOUT
        self.default_model = DEFAULT_MODEL

    def execute(
        self,
        prompt: str,
        model: str | None = None,
        task_id: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Execute an agent task through the worker."""

        if not prompt or not prompt.strip():
            raise ValueError("Task prompt cannot be empty.")

        selected_model = model or self.default_model
        selected_timeout = timeout_seconds or self.timeout

        task = {
            "task_id": task_id,
            "prompt": prompt.strip(),
            "model": selected_model,
            "timeout": selected_timeout,
        }

        result = self.worker_client.execute_task(task)

        return {
            "task_id": task_id,
            "model": selected_model,
            "result": result,
        }

    def health_check(self) -> dict[str, Any]:
        """Check whether the worker is reachable."""

        return self.worker_client.health_check()
