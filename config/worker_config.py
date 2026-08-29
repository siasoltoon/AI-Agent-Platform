"""
Worker Configuration

Central configuration for communication between the AI Agent Platform
controller and the execution worker, including large-task execution.
"""

import os

from dotenv import load_dotenv


load_dotenv()

WORKER_HOST = os.getenv("WORKER_HOST", "127.0.0.1")
WORKER_PORT = int(os.getenv("WORKER_PORT", "8001"))

# Controller -> worker request timeout.
WORKER_TIMEOUT = int(os.getenv("WORKER_TIMEOUT", "300"))

# Large tasks may require several model calls.
LARGE_TASK_TIMEOUT = int(os.getenv("LARGE_TASK_TIMEOUT", "1800"))

# Prompt length is never rejected by the API. This threshold only selects
# the multi-step execution path; Ollama/model context limits remain the
# final feasibility boundary.
LARGE_TASK_THRESHOLD = int(os.getenv("LARGE_TASK_THRESHOLD", "12000"))

# Keep the number of generated execution steps bounded and predictable.
MAX_PLAN_STEPS = int(os.getenv("MAX_PLAN_STEPS", "12"))

# Per-step result included in the next model context.
STEP_CONTEXT_CHARS = int(os.getenv("STEP_CONTEXT_CHARS", "12000"))

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "qwen2.5-coder:7b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
