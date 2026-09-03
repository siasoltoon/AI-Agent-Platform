"""Ollama local model integration service."""

from __future__ import annotations

import json
import threading
from typing import Any

import requests


OLLAMA_TIMEOUT_MARGIN_SECONDS = 5


class OllamaService:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:7b",
        timeout: int = 120,
        cancel_event: threading.Event | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.cancel_event = cancel_event

    @property
    def cancelled(self) -> bool:
        return bool(self.cancel_event and self.cancel_event.is_set())

    @staticmethod
    def _expects_json_action(prompt: str) -> bool:
        lowered = prompt.lower()
        return "return exactly one json object" in lowered or '"action":"tool"' in lowered

    def _raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise StopIteration("Ollama generation cancelled.")

    def _generate_once(self, payload: dict[str, Any], request_timeout: int) -> dict[str, Any]:
        self._raise_if_cancelled()
        response = None
        try:
            # Streaming lets the worker observe cancellation while Ollama is
            # still generating instead of waiting for a monolithic response.
            streaming_payload = dict(payload)
            streaming_payload["stream"] = True
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=streaming_payload,
                timeout=request_timeout,
                stream=True,
            )
            response.raise_for_status()
            chunks: list[str] = []
            final_data: dict[str, Any] = {}
            for line in response.iter_lines(decode_unicode=True):
                self._raise_if_cancelled()
                if not line:
                    continue
                item = json.loads(line)
                if isinstance(item, dict):
                    final_data = item
                    piece = item.get("response")
                    if piece:
                        chunks.append(str(piece))
                    if item.get("done") is True:
                        break
            final_data["response"] = "".join(chunks)
            return final_data
        finally:
            if response is not None:
                response.close()

    def generate(
        self,
        prompt: str,
        timeout: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a response while supporting timeout and cooperative cancellation."""
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        self._raise_if_cancelled()
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
        request_timeout = max(1, request_timeout - OLLAMA_TIMEOUT_MARGIN_SECONDS)
        data = self._generate_once(payload, request_timeout)

        if agent_json:
            raw = str(data.get("response", "")).strip()
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                self._raise_if_cancelled()
                correction = (
                    "Your previous response was not valid JSON. Retry the same action now. "
                    "Return ONLY one valid JSON object, with no markdown, explanation, or code fence.\n\n"
                    f"Original task/context:\n{prompt}"
                )
                retry_payload = {**payload, "prompt": correction}
                data = self._generate_once(retry_payload, request_timeout)
                raw = str(data.get("response", "")).strip()
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError("Ollama returned malformed JSON after corrective retry.") from exc

            if not isinstance(parsed, dict):
                raise ValueError("Ollama returned a JSON value, but the agent action must be an object.")

        return data
