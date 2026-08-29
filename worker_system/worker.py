"""HTTP execution worker for the AI Agent Platform."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.services.ollama_service import OllamaService
from config.worker_config import DEFAULT_MODEL, OLLAMA_HOST


class ExecuteRequest(BaseModel):
    task: str | None = None
    prompt: str | None = None
    model: str | None = None
    task_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Worker:
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.status = "idle"

    def execute(self, job: dict[str, Any]) -> dict[str, Any]:
        self.status = "running"
        try:
            prompt = job.get("prompt") or job.get("task")
            if not prompt:
                raise ValueError("Task prompt is required.")

            model = job.get("model") or DEFAULT_MODEL
            service = OllamaService(base_url=OLLAMA_HOST, model=model)
            response = service.generate(prompt)

            return {
                "status": "completed",
                "worker_id": self.worker_id,
                "task_id": job.get("task_id"),
                "model": model,
                "result": response.get("response", ""),
                "raw": response,
            }
        finally:
            self.status = "idle"


worker = Worker("pc-worker-01")
app = FastAPI(title="AI Agent Platform Worker", version="0.1.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "worker_id": worker.worker_id,
        "worker_status": worker.status,
        "ollama": OLLAMA_HOST,
        "model": DEFAULT_MODEL,
    }


@app.post("/execute")
def execute(request: ExecuteRequest) -> dict[str, Any]:
    try:
        return worker.execute(request.model_dump())
    except Exception as exc:
        worker.status = "idle"
        raise HTTPException(
            status_code=500,
            detail={"message": "Worker execution failed.", "error": str(exc)},
        ) from exc
