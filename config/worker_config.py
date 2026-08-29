"""
Worker Configuration

Central configuration for communication between
the AI Agent Platform controller and the execution worker.
"""

import os

from dotenv import load_dotenv


# Load local .env configuration when present.
load_dotenv()


# Worker connection
# The controller runs on the laptop; the worker runs on the PC.
WORKER_HOST = os.getenv(
    "WORKER_HOST",
    "127.0.0.1"
)

WORKER_PORT = int(
    os.getenv(
        "WORKER_PORT",
        "8001"
    )
)


# Request timeout
WORKER_TIMEOUT = int(
    os.getenv(
        "WORKER_TIMEOUT",
        "300"
    )
)


# Ollama model
DEFAULT_MODEL = os.getenv(
    "DEFAULT_MODEL",
    "qwen2.5-coder:7b"
)


# Ollama endpoint
# Ollama is accessed by the worker locally on the PC.
OLLAMA_HOST = os.getenv(
    "OLLAMA_HOST",
    "http://127.0.0.1:11434"
)
