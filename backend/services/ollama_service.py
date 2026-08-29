"""Ollama local model integration service."""

from __future__ import annotations

from typing import Any

import requests


class OllamaService:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:7b",
        timeout: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        timeout: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a non-streaming response with configurable runtime limits."""
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                # Do not artificially stop long agent responses.
                "num_predict": -1,
            },
        }

        if options:
            payload["options"].update(options)

        response = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=timeout or self.timeout,
        )
        response.raise_for_status()
        return response.json()
