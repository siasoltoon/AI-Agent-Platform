"""
Agent Runtime

Coordinates task execution between the Agent Core, Task Engine and PC Worker.
Large missions automatically use a multi-step planner/executor/finalizer path.
"""

from __future__ import annotations

from typing import Any

from agent_core.large_task import LargeTaskOrchestrator
from backend.services.worker_client import WorkerClient
from config.worker_config import (
    DEFAULT_MODEL,
    LARGE_TASK_THRESHOLD,
    LARGE_TASK_TIMEOUT,
    MAX_PLAN_STEPS,
    MAX_STEP_RETRIES,
    MISSION_CHUNK_CHARS,
    MISSION_CONTEXT_CHARS,
    STEP_CONTEXT_CHARS,
    WORKER_HOST,
    WORKER_PORT,
    WORKER_TIMEOUT,
)


MAX_RUNTIME_TIMEOUT = 1800


class AgentRuntime:
    def __init__(self, worker_client: WorkerClient | None = None):
        self.worker_client = worker_client or WorkerClient(host=WORKER_HOST, port=WORKER_PORT)
        self.timeout = WORKER_TIMEOUT
        self.large_task_timeout = LARGE_TASK_TIMEOUT
        self.default_model = DEFAULT_MODEL
        self.large_task_threshold = LARGE_TASK_THRESHOLD

    def _generate(
        self,
        prompt: str,
        model: str,
        timeout: int,
        task_id: str | None,
        phase: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.worker_client.execute_task(
            {
                "task_id": task_id,
                "prompt": prompt,
                "model": model,
                "timeout": timeout,
                "metadata": {"phase": phase, **(metadata or {})},
            },
            timeout=timeout,
        )
        return {"response": response.get("result", ""), "raw": response}

    @staticmethod
    def _bounded_timeout(value: int, *, field: str = "timeout_seconds") -> int:
        if value < 1 or value > MAX_RUNTIME_TIMEOUT:
            raise ValueError(f"{field} must be between 1 and {MAX_RUNTIME_TIMEOUT} seconds.")
        return value

    @staticmethod
    def _validate_worker_result(response: dict[str, Any]) -> None:
        """Reject false-positive worker responses before a task can be marked completed."""
        if not isinstance(response, dict):
            raise RuntimeError("Worker returned an invalid execution response without verified execution evidence.")
        if response.get("status") != "completed":
            raise RuntimeError("Worker did not report a completed execution.")
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Worker returned no structured execution result or verified execution evidence.")
        evidence = result.get("execution_evidence")
        if not isinstance(evidence, dict) or evidence.get("verified") is not True:
            raise RuntimeError("Worker reported completion without verified execution evidence.")
        tool_records = result.get("tool_records")
        if not isinstance(tool_records, list) or not any(
            isinstance(record, dict) and record.get("ok") is True for record in tool_records
        ):
            raise RuntimeError("Worker reported completion without a successful tool action.")

    def execute(
        self,
        prompt: str,
        model: str | None = None,
        task_id: str | None = None,
        timeout_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a task through the real agentic PC-worker path."""
        if not prompt or not prompt.strip():
            raise ValueError("Task prompt cannot be empty.")

        prompt = prompt.strip()
        selected_model = model or self.default_model
        is_large = len(prompt) >= self.large_task_threshold
        default_timeout = self.large_task_timeout if is_large else self.timeout
        selected_timeout = self._bounded_timeout(
            int(timeout_seconds) if timeout_seconds is not None else int(default_timeout)
        )
        execution_metadata = dict(metadata or {})

        if not is_large:
            result = self.worker_client.execute_task(
                {
                    "task_id": task_id,
                    "prompt": prompt,
                    "model": selected_model,
                    "timeout": selected_timeout,
                    "metadata": execution_metadata,
                },
                timeout=selected_timeout,
            )
            self._validate_worker_result(result)
            return {
                "task_id": task_id,
                "model": selected_model,
                "execution_mode": "agentic",
                "result": result,
            }

        orchestrator = LargeTaskOrchestrator(
            generate=lambda p, timeout: self._generate(
                p,
                selected_model,
                self._bounded_timeout(int(timeout), field="step_timeout"),
                task_id,
                "large_task",
                execution_metadata,
            ),
            threshold=self.large_task_threshold,
            max_steps=MAX_PLAN_STEPS,
            max_retries=MAX_STEP_RETRIES,
            context_chars=STEP_CONTEXT_CHARS,
            mission_context_chars=MISSION_CONTEXT_CHARS,
            mission_chunk_chars=MISSION_CHUNK_CHARS,
        )
        orchestration = orchestrator.execute(prompt=prompt, model=selected_model, timeout=selected_timeout)
        return {
            "task_id": task_id,
            "model": selected_model,
            "execution_mode": "multi_step_agentic",
            "result": orchestration,
        }

    def health_check(self) -> dict[str, Any]:
        return self.worker_client.health_check()
