"""HTTP execution worker for the AI Agent Platform."""

from __future__ import annotations

import logging
import threading
import time
import traceback
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from agent_core.execution_agent import AgentExecutionError, AgentExecutor
from backend.services.ollama_service import OllamaService
from config.worker_config import DEFAULT_MODEL, OLLAMA_HOST, WORKER_TIMEOUT

logger = logging.getLogger("ai_agent_worker")

MAX_PROMPT_CHARS = 200_000
MAX_TASK_ID_CHARS = 128
MAX_MODEL_CHARS = 128
MAX_TIMEOUT_SECONDS = 1800
MAX_METADATA_KEYS = 64
MAX_AGENT_STEPS = 32


class ExecuteRequest(BaseModel):
    task: str | None = None
    prompt: str | None = Field(default=None, max_length=MAX_PROMPT_CHARS)
    model: str | None = Field(default=None, max_length=MAX_MODEL_CHARS)
    task_id: str | None = Field(default=None, max_length=MAX_TASK_ID_CHARS)
    timeout: int | None = Field(default=None, ge=1, le=MAX_TIMEOUT_SECONDS)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prompt", "task")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("model", "task_id")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > MAX_METADATA_KEYS:
            raise ValueError(f"Task metadata cannot contain more than {MAX_METADATA_KEYS} keys.")
        return value


class Worker:
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.status = "idle"
        self.started_at: float | None = None
        self.last_completed_at: float | None = None
        self.last_error: str | None = None
        self._execution_lock = threading.Lock()

    def execute(self, job: dict[str, Any]) -> dict[str, Any]:
        if not self._execution_lock.acquire(blocking=False):
            raise RuntimeError("Worker is busy executing another task.")
        self.status = "running"
        self.started_at = time.time()
        self.last_error = None
        try:
            prompt = job.get("prompt") or job.get("task")
            if not prompt or not str(prompt).strip():
                raise ValueError("Task prompt is required.")
            prompt = str(prompt).strip()
            if len(prompt) > MAX_PROMPT_CHARS:
                raise ValueError(f"Task prompt cannot exceed {MAX_PROMPT_CHARS} characters.")

            model = str(job.get("model") or DEFAULT_MODEL).strip()
            if not model or len(model) > MAX_MODEL_CHARS:
                raise ValueError(f"Model identifier must be between 1 and {MAX_MODEL_CHARS} characters.")

            timeout = int(job.get("timeout") or WORKER_TIMEOUT)
            if timeout < 1 or timeout > MAX_TIMEOUT_SECONDS:
                raise ValueError(f"Worker timeout must be between 1 and {MAX_TIMEOUT_SECONDS} seconds.")

            metadata = job.get("metadata") or {}
            if not isinstance(metadata, dict) or len(metadata) > MAX_METADATA_KEYS:
                raise ValueError(f"Task metadata cannot contain more than {MAX_METADATA_KEYS} keys.")
            workspace = metadata.get("workspace")

            # Keep the runtime default aligned with the worker's published contract.
            # Callers may request a smaller bounded budget, but omission must not
            # silently downgrade the execution contract to a different default.
            requested_steps = int(metadata.get("max_agent_steps", MAX_AGENT_STEPS))
            if requested_steps < 1 or requested_steps > MAX_AGENT_STEPS:
                raise ValueError(f"max_agent_steps must be between 1 and {MAX_AGENT_STEPS}.")

            logger.info("Executing task_id=%s model=%s prompt_length=%s timeout=%s mode=agentic max_agent_steps=%s", job.get("task_id"), model, len(prompt), timeout, requested_steps)
            service = OllamaService(base_url=OLLAMA_HOST, model=model, timeout=timeout)
            executor = AgentExecutor(service, workspace_root=workspace, max_steps=requested_steps)
            result = executor.execute(prompt)

            if result.get("status") != "completed" or not result.get("execution_evidence", {}).get("verified", False):
                raise AgentExecutionError("Agent execution completed without verified execution evidence.")

            self.last_completed_at = time.time()
            return {"status": "completed", "worker_id": self.worker_id, "task_id": job.get("task_id"), "model": model, "result": result}
        except Exception as exc:
            self.last_error = str(exc)
            raise
        finally:
            self.status = "idle"
            self.started_at = None
            self._execution_lock.release()


worker = Worker("pc-worker-01")
app = FastAPI(title="AI Agent Platform Worker", version="0.5.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "worker_id": worker.worker_id,
        "worker_status": worker.status,
        "ollama": OLLAMA_HOST,
        "model": DEFAULT_MODEL,
        "execution_mode": "agentic",
        "max_timeout_seconds": MAX_TIMEOUT_SECONDS,
        "max_agent_steps": MAX_AGENT_STEPS,
        "last_completed_at": worker.last_completed_at,
        "last_error": worker.last_error,
    }


@app.post("/execute")
def execute(request: ExecuteRequest) -> dict[str, Any]:
    try:
        return worker.execute(request.model_dump())
    except (AgentExecutionError, ValueError, RuntimeError) as exc:
        logger.error("Agent execution failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=422, detail={"message": "Agent could not complete the task.", "error": str(exc), "task_id": request.task_id}) from exc
    except Exception as exc:
        worker.status = "idle"
        logger.error("Worker execution failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail={"message": "Worker execution failed.", "error_type": type(exc).__name__, "error": str(exc), "task_id": request.task_id}) from exc
