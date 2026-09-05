"""
Worker Configuration

Central configuration for communication between the AI Agent Platform
controller and the execution worker, including large-task execution.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

WORKER_HOST = os.getenv("WORKER_HOST", "127.0.0.1")
WORKER_PORT = int(os.getenv("WORKER_PORT", "8001"))
WORKER_TIMEOUT = int(os.getenv("WORKER_TIMEOUT", "900"))
LARGE_TASK_TIMEOUT = int(os.getenv("LARGE_TASK_TIMEOUT", "1800"))
LARGE_TASK_THRESHOLD = int(os.getenv("LARGE_TASK_THRESHOLD", "12000"))
MAX_PLAN_STEPS = int(os.getenv("MAX_PLAN_STEPS", "12"))
MAX_STEP_RETRIES = int(os.getenv("MAX_STEP_RETRIES", "1"))
STEP_CONTEXT_CHARS = int(os.getenv("STEP_CONTEXT_CHARS", "12000"))
MISSION_CONTEXT_CHARS = int(os.getenv("MISSION_CONTEXT_CHARS", "28000"))
MISSION_CHUNK_CHARS = int(os.getenv("MISSION_CHUNK_CHARS", "16000"))

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "qwen2.5-coder:7b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
# Every worker execution must remain below this host-level workspace boundary.
# Defaults to the worker process working directory so existing deployments do
# not need an immediate environment change.
WORKER_ISOLATION_ROOT = str(Path(os.getenv("WORKER_ISOLATION_ROOT", Path.cwd())).expanduser().resolve())
