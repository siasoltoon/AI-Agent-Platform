"""Canonical task contracts shared by the controller and task engine."""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


MAX_PROMPT_CHARS = 200_000
MAX_TASK_ID_CHARS = 128
MAX_MODEL_CHARS = 128
MAX_TIMEOUT_SECONDS = 1800
MAX_METADATA_KEYS = 64
MAX_METADATA_CHARS = 32_768


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskRequest(BaseModel):
    """Canonical request accepted by the controller task API."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=MAX_PROMPT_CHARS,
        description="Task instruction. Limited to a bounded size before execution.",
    )
    model: str | None = Field(
        default=None,
        max_length=MAX_MODEL_CHARS,
        description="Optional bounded model identifier. Uses the configured default when omitted.",
    )
    task_id: str | None = Field(
        default=None,
        max_length=MAX_TASK_ID_CHARS,
        description="Optional caller-supplied task identifier.",
    )
    timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        le=MAX_TIMEOUT_SECONDS,
        description="Optional execution timeout override, capped at 30 minutes.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Task prompt cannot be empty.")
        return value

    @field_validator("model")
    @classmethod
    def normalize_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("task_id")
    @classmethod
    def normalize_task_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > MAX_METADATA_KEYS:
            raise ValueError(f"Task metadata cannot contain more than {MAX_METADATA_KEYS} keys.")
        try:
            serialized = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            raise ValueError("Task metadata must be JSON-serializable.") from exc
        if len(serialized) > MAX_METADATA_CHARS:
            raise ValueError(f"Task metadata cannot exceed {MAX_METADATA_CHARS} characters.")
        return value


class TaskResponse(BaseModel):
    """Canonical task state returned by the controller."""

    id: str
    prompt: str
    model: str | None
    status: TaskStatus
    created_at: float
    started_at: float | None = None
    completed_at: float | None = None
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
