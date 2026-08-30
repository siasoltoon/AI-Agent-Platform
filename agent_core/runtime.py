"""Agent runtime boundary for real PC-worker execution."""

from __future__ import annotations

from typing import Any

from backend.services.worker_client import WorkerClient
from config.worker_config import DEFAULT_MODEL, LARGE_TASK_THRESHOLD, LARGE_TASK_TIMEOUT, WORKER_HOST, WORKER_PORT, WORKER_TIMEOUT

MAX_RUNTIME_TIMEOUT = 1800
DEFAULT_LARGE_AGENT_STEPS = 64
DEFAULT_NORMAL_AGENT_STEPS = 24


class AgentRuntime:
    def __init__(self, worker_client: WorkerClient | None = None):
        self.worker_client = worker_client or WorkerClient(host=WORKER_HOST, port=WORKER_PORT)
        self.timeout = WORKER_TIMEOUT
        self.large_task_timeout = LARGE_TASK_TIMEOUT
        self.default_model = DEFAULT_MODEL
        self.large_task_threshold = LARGE_TASK_THRESHOLD

    @staticmethod
    def _bounded_timeout(value: int, *, field: str = "timeout_seconds") -> int:
        if value < 1 or value > MAX_RUNTIME_TIMEOUT:
            raise ValueError(f"{field} must be between 1 and {MAX_RUNTIME_TIMEOUT} seconds.")
        return value

    @staticmethod
    def _validate_worker_result(response: dict[str, Any]) -> None:
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
        if not isinstance(tool_records, list) or not any(isinstance(record, dict) and record.get("ok") is True for record in tool_records):
            raise RuntimeError("Worker reported completion without a successful tool action.")

    def execute(self, prompt: str, model: str | None = None, task_id: str | None = None,
                timeout_seconds: int | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not prompt or not prompt.strip():
            raise ValueError("Task prompt cannot be empty.")
        prompt = prompt.strip()
        selected_model = (model or self.default_model).strip()
        if not selected_model:
            raise ValueError("Model identifier cannot be empty.")

        is_large = len(prompt) >= self.large_task_threshold
        selected_timeout = self._bounded_timeout(int(timeout_seconds) if timeout_seconds is not None else int(self.large_task_timeout if is_large else self.timeout))
        execution_metadata = dict(metadata or {})
        configured_steps = execution_metadata.get("max_agent_steps")
        if configured_steps is None:
            configured_steps = DEFAULT_LARGE_AGENT_STEPS if is_large else DEFAULT_NORMAL_AGENT_STEPS
        try:
            requested_steps = int(configured_steps)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_agent_steps must be an integer.") from exc
        maximum = DEFAULT_LARGE_AGENT_STEPS if is_large else DEFAULT_NORMAL_AGENT_STEPS
        if requested_steps < 1 or requested_steps > maximum:
            raise ValueError(f"max_agent_steps must be between 1 and {maximum} for this execution profile.")
        execution_metadata["max_agent_steps"] = requested_steps
        execution_metadata["execution_profile"] = "large" if is_large else "normal"

        payload = {"task_id": task_id, "prompt": prompt, "model": selected_model, "timeout": selected_timeout, "metadata": execution_metadata}
        result = self.worker_client.execute_task(payload, timeout=selected_timeout)
        self._validate_worker_result(result)
        return {"task_id": task_id, "model": selected_model, "execution_mode": "agentic_large" if is_large else "agentic", "result": result}

    def health_check(self) -> dict[str, Any]:
        return self.worker_client.health_check()
