"""Ollama local model integration service."""

from __future__ import annotations

import json
from typing import Any

import requests


# Keep the local model request slightly below the controller/worker HTTP
# deadline. This prevents the controller from timing out while the worker is
# still holding an active Ollama generation for the same task id.
OLLAMA_TIMEOUT_MARGIN_SECONDS = 5


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

    @staticmethod
    def _expects_json_action(prompt: str) -> bool:
        lowered = prompt.lower()
        return "return exactly one json object" in lowered or '"action":"tool"' in lowered

    def generate(
        self,
        prompt: str,
        timeout: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a non-streaming response with a worker-safe runtime limit."""
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        agent_json = self._expects_json_action(prompt)
        request_options: dict[str, Any] = {"num_predict": -1}
        if options:
            request_options.update(options)
        if agent_json:
            request_options.setdefault("temperature", 0)

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": request_options,
        }
        if agent_json:
            payload["format"] = "json"

        request_timeout = timeout or self.timeout
        # The controller's timeout must remain the outer boundary. Give the
        # worker a small margin to receive Ollama's timeout and release its
        # task-id/in-flight state before the controller can retry anything.
        request_timeout = max(1, request_timeout - OLLAMA_TIMEOUT_MARGIN_SECONDS)
        response = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=request_timeout,
        )
        response.raise_for_status()
        data = response.json()

        if agent_json:
            raw = str(data.get("response", "")).strip()
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                correction = (
                    "Your previous response was not valid JSON. Retry the same action now. "
                    "Return ONLY one valid JSON object, with no markdown, explanation, or code fence.\n\n"
                    f"Original task/context:\n{prompt}"
                )
                retry_payload = {**payload, "prompt": correction}
                retry = requests.post(
                    f"{self.base_url}/api/generate",
                    json=retry_payload,
                    timeout=request_timeout,
                )
                retry.raise_for_status()
                data = retry.json()
                raw = str(data.get("response", "")).strip()
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError("Ollama returned malformed JSON after corrective retry.") from exc

            if not isinstance(parsed, dict):
                raise ValueError("Ollama returned a JSON value, but the agent action must be an object.")

        return data
