"""
Agent Runtime

Coordinates task execution between the Agent Core,
Task Engine and Worker layer.
"""

from typing import Optional, Dict, Any

from backend.services.worker_client import WorkerClient
from config.worker_config import (
    WORKER_HOST,
    WORKER_PORT,
    WORKER_TIMEOUT,
    DEFAULT_MODEL,
)


class AgentRuntime:

    def __init__(
        self,
        worker_client: Optional[WorkerClient] = None,
    ):
        self.worker_client = worker_client or WorkerClient(
            host=WORKER_HOST,
            port=WORKER_PORT,
        )

        self.timeout = WORKER_TIMEOUT
        self.default_model = DEFAULT_MODEL

    def execute(
        self,
        prompt: str,
        model: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute an agent task through the worker.
        """

        if not prompt or not prompt.strip():
            raise ValueError(
                "Task prompt cannot be empty."
            )

        selected_model = (
            model
            or self.default_model
        )

        task = {
            "task_id": task_id,
            "prompt": prompt.strip(),
            "model": selected_model,
            "timeout": self.timeout,
        }

        result = self.worker_client.execute_task(
            task
        )

        return {
            "task_id": task_id,
            "model": selected_model,
            "result": result,
        }

    def health_check(self) -> Dict[str, Any]:
        """
        Check whether the worker is reachable.
        """

        return self.worker_client.health_check()
