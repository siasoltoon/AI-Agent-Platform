"""HTTP execution worker for the AI Agent Platform."""

from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent_core.execution_agent import AgentExecutionError, AgentExecutor
from backend.services.ollama_service import OllamaService
from config.worker_config import DEFAULT_MODEL, OLLAMA_HOST, WORKER_TIMEOUT

logger = logging.getLogger("ai_agent_worker")


class ExecuteRequest(BaseModel):
    task: str | None = None
    prompt: str | None = None
    model: str | None = None
    task_id: str | None = None
    timeout: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Worker:
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.status = "idle"

    def execute(self, job: dict[str, Any]) -> dict[str, Any]:
        self.status = "running"
        try:
            prompt = job.get("prompt") or job.get("task")
            if not prompt or not str(prompt).strip():
                raise ValueError("Task prompt is required.")

            model = job.get("model") or DEFAULT_MODEL
            timeout = int(job.get("timeout") or WORKER_TIMEOUT)
            metadata = job.get("metadata") or {}
            workspace = metadata.get("workspace")

            logger.info(
                "Executing task_id=%s model=%s prompt_length=%s timeout=%s mode=agentic",
                job.get("task_id"), model, len(prompt), timeout,
            )

            service = OllamaService(base_url=OLLAMA_HOST, model=model, timeout=timeout)
            executor = AgentExecutor(
                service,
                workspace_root=workspace,
                max_steps=int(metadata.get("max_agent_steps", 12)),
            )
            result = executor.execute(str(prompt))

            return {
                "status": "completed",
                "worker_id": self.worker_id,
                "task_id": job.get("task_id"),
                "model": model,
                "result": result,
            }
        finally:
            self.status = "idle"


worker = Worker("pc-worker-01")
app = FastAPI(title="AI Agent Platform Worker", version="0.3.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "worker_id": worker.worker_id,
        "worker_status": worker.status,
        "ollama": OLLAMA_HOST,
        "model": DEFAULT_MODEL,
        "execution_mode": "agentic",
    }


@app.post("/execute")
def execute(request: ExecuteRequest) -> dict[str, Any]:
    try:
        return worker.execute(request.model_dump())
    except (AgentExecutionError, ValueError) as exc:
        logger.error("Agent execution failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(
            status_code=422,
            detail={"message": "Agent could not complete the task.", "error": str(exc), "task_id": request.task_id},
        ) from exc
    except Exception as exc:
        worker.status = "idle"
        logger.error("Worker execution failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail={"message": "Worker execution failed.", "error_type": type(exc).__name__, "error": str(exc), "task_id": request.task_id},
        ) from exc
