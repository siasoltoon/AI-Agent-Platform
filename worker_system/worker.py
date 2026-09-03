"""HTTP execution worker for the AI Agent Platform."""

from __future__ import annotations

import copy
import logging
import threading
import time
import traceback
from collections import OrderedDict
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from agent_core.execution_agent import AgentExecutionError
from agent_core.reliable_executor import ReliableAgentExecutor
from backend.services.ollama_service import OllamaService
from backend.services.telemetry import snapshot as resource_snapshot
from config.worker_config import DEFAULT_MODEL, OLLAMA_HOST, WORKER_TIMEOUT

logger = logging.getLogger("ai_agent_worker")

MAX_PROMPT_CHARS = 200_000
MAX_TASK_ID_CHARS = 128
MAX_MODEL_CHARS = 128
MAX_TIMEOUT_SECONDS = 1800
MAX_METADATA_KEYS = 64
MAX_NORMAL_AGENT_STEPS = 32
MAX_LARGE_AGENT_STEPS = 64
MAX_IDEMPOTENCY_ENTRIES = 256
MAX_AGENT_STEPS = MAX_LARGE_AGENT_STEPS

AgentExecutor = ReliableAgentExecutor


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
        self._idempotency_lock = threading.Lock()
        self._cancellation_lock = threading.Lock()
        self._completed_results: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._inflight_task_ids: set[str] = set()
        self._cancellation_events: dict[str, threading.Event] = {}

    def _claim_task_id(self, task_id: str | None) -> dict[str, Any] | None:
        if not task_id:
            return None
        with self._idempotency_lock:
            cached = self._completed_results.get(task_id)
            if cached is not None:
                self._completed_results.move_to_end(task_id)
                replayed = copy.deepcopy(cached)
                replayed["idempotency"] = {"key": task_id, "replayed": True}
                return replayed
            if task_id in self._inflight_task_ids:
                raise RuntimeError(f"Execution for task_id={task_id} is already in progress; duplicate execution rejected.")
            self._inflight_task_ids.add(task_id)
        return None

    def _store_result(self, task_id: str | None, result: dict[str, Any]) -> None:
        if not task_id:
            return
        with self._idempotency_lock:
            self._inflight_task_ids.discard(task_id)
            self._completed_results[task_id] = copy.deepcopy(result)
            self._completed_results.move_to_end(task_id)
            while len(self._completed_results) > MAX_IDEMPOTENCY_ENTRIES:
                self._completed_results.popitem(last=False)

    def _release_task_id(self, task_id: str | None) -> None:
        if task_id:
            with self._idempotency_lock:
                self._inflight_task_ids.discard(task_id)

    def _register_cancellation(self, task_id: str | None) -> threading.Event | None:
        if not task_id:
            return None
        event = threading.Event()
        with self._cancellation_lock:
            self._cancellation_events[task_id] = event
        return event

    def _release_cancellation(self, task_id: str | None) -> None:
        if task_id:
            with self._cancellation_lock:
                self._cancellation_events.pop(task_id, None)

    def cancel(self, task_id: str) -> bool:
        task_id = str(task_id or "").strip()
        if not task_id:
            return False
        with self._cancellation_lock:
            event = self._cancellation_events.get(task_id)
            if event is None:
                logger.warning("Cancellation requested for task_id=%s but task is not inflight", task_id)
                return False
            event.set()
            logger.warning("Cancellation event set for task_id=%s", task_id)
            return True

    def is_cancelled(self, task_id: str | None) -> bool:
        if not task_id:
            return False
        with self._cancellation_lock:
            event = self._cancellation_events.get(task_id)
            return bool(event and event.is_set())

    def execute(self, job: dict[str, Any]) -> dict[str, Any]:
        task_id = str(job.get("task_id") or "").strip() or None
        execution_started = time.monotonic()
        cached = self._claim_task_id(task_id)
        if cached is not None:
            logger.info("Returning cached idempotent result for task_id=%s", task_id)
            return cached

        if not self._execution_lock.acquire(blocking=False):
            self._release_task_id(task_id)
            raise RuntimeError("Worker is busy executing another task.")
        cancellation_event = self._register_cancellation(task_id)
        self.status = "running"
        self.started_at = time.time()
        self.last_error = None
        logger.info("Task execution started task_id=%s", task_id)
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

            execution_profile = str(metadata.get("execution_profile", "normal")).strip().lower()
            if execution_profile not in {"normal", "large"}:
                raise ValueError("execution_profile must be either 'normal' or 'large'.")
            maximum_steps = MAX_LARGE_AGENT_STEPS if execution_profile == "large" else MAX_NORMAL_AGENT_STEPS
            requested_steps = int(metadata.get("max_agent_steps", maximum_steps))
            if requested_steps < 1 or requested_steps > maximum_steps:
                raise ValueError(
                    f"max_agent_steps must be between 1 and {maximum_steps} for the {execution_profile} execution profile."
                )

            logger.info(
                "Executing task_id=%s model=%s prompt_length=%s timeout=%s mode=agentic-reliable profile=%s max_agent_steps=%s self_repair_attempts=%s",
                task_id, model, len(prompt), timeout, execution_profile, requested_steps, ReliableAgentExecutor.MAX_ATTEMPTS,
            )
            service = OllamaService(base_url=OLLAMA_HOST, model=model, timeout=timeout, cancel_event=cancellation_event)
            executor = AgentExecutor(service, workspace_root=workspace, max_steps=requested_steps)
            result = executor.execute(prompt)

            if cancellation_event is not None and cancellation_event.is_set():
                logger.warning("Cancellation detected after executor returned task_id=%s elapsed_ms=%.1f", task_id, (time.monotonic() - execution_started) * 1000)
                raise AgentExecutionError("Task execution was cancelled.")
            if result.get("status") != "completed" or not result.get("execution_evidence", {}).get("verified", False):
                raise AgentExecutionError("Agent execution completed without verified execution evidence.")

            self.last_completed_at = time.time()
            response = {
                "status": "completed",
                "worker_id": self.worker_id,
                "task_id": task_id,
                "model": model,
                "execution_profile": execution_profile,
                "max_agent_steps": requested_steps,
                "result": result,
                "resource_snapshot": resource_snapshot(),
                "idempotency": {"key": task_id, "replayed": False},
            }
            self._store_result(task_id, response)
            return response
        except Exception as exc:
            self.last_error = str(exc)
            self._release_task_id(task_id)
            logger.warning("Task execution exiting with error task_id=%s error_type=%s elapsed_ms=%.1f", task_id, type(exc).__name__, (time.monotonic() - execution_started) * 1000)
            raise
        finally:
            self._release_cancellation(task_id)
            self.status = "idle"
            self.started_at = None
            self._execution_lock.release()
            logger.info("Task execution cleanup complete task_id=%s cancelled=%s total_elapsed_ms=%.1f", task_id, bool(cancellation_event and cancellation_event.is_set()), (time.monotonic() - execution_started) * 1000)


worker = Worker("pc-worker-01")
app = FastAPI(title="AI Agent Platform Worker", version="0.7.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "worker_id": worker.worker_id,
        "worker_status": worker.status,
        "ollama": OLLAMA_HOST,
        "model": DEFAULT_MODEL,
        "execution_mode": "agentic-reliable",
        "max_timeout_seconds": MAX_TIMEOUT_SECONDS,
        "max_agent_steps": MAX_AGENT_STEPS,
        "normal_agent_steps": MAX_NORMAL_AGENT_STEPS,
        "large_agent_steps": MAX_LARGE_AGENT_STEPS,
        "self_repair_attempts": ReliableAgentExecutor.MAX_ATTEMPTS,
        "idempotency": {"enabled": True, "scope": "worker-process", "max_entries": MAX_IDEMPOTENCY_ENTRIES},
        "cancellation": {"enabled": True, "scope": "worker-process", "inflight_only": True},
        "last_completed_at": worker.last_completed_at,
        "last_error": worker.last_error,
        "resources": resource_snapshot(),
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


@app.post("/cancel/{task_id}")
def cancel(task_id: str) -> dict[str, Any]:
    if worker.cancel(task_id):
        logger.warning("Cancellation requested for task_id=%s", task_id)
        return {"status": "cancellation_requested", "task_id": task_id}
    return {"status": "not_inflight", "task_id": task_id}
