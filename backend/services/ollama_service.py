"""Ollama local model integration service."""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from typing import Any

import requests


logger = logging.getLogger("ai_agent_ollama")
OLLAMA_TIMEOUT_MARGIN_SECONDS = 5
OLLAMA_CONNECT_TIMEOUT_SECONDS = 3


class OllamaService:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5-coder:7b", timeout: int = 120, cancel_event: threading.Event | None = None):
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
        return "return exactly one json object" in lowered or '\"action\":\"tool\"' in lowered

    def _raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise StopIteration("Ollama generation cancelled.")

    @staticmethod
    def _hard_abort_response(response: Any) -> None:
        """Best-effort hard abort of the underlying HTTP socket."""
        started = time.monotonic()
        raw = getattr(response, "raw", None)
        candidates: list[Any] = [
            getattr(raw, "_connection", None),
            getattr(raw, "_sock", None),
        ]
        fp = getattr(raw, "_fp", None)
        fp_fp = getattr(fp, "fp", None)
        fp_raw = getattr(fp_fp, "raw", None)
        candidates.extend([
            getattr(fp_raw, "_sock", None),
            fp_raw,
        ])

        seen: set[int] = set()
        for candidate in candidates:
            if candidate is None or id(candidate) in seen:
                continue
            seen.add(id(candidate))
            sock = getattr(candidate, "sock", candidate)
            try:
                shutdown = getattr(sock, "shutdown", None)
                if callable(shutdown):
                    shutdown(socket.SHUT_RDWR)
            except (OSError, AttributeError):
                pass
            try:
                close = getattr(sock, "close", None)
                if callable(close):
                    close()
            except (OSError, AttributeError):
                pass

        try:
            response.close()
        except (OSError, AttributeError):
            pass
        logger.info("Ollama response hard-abort completed elapsed_ms=%.1f", (time.monotonic() - started) * 1000)

    def _generate_once(self, payload: dict[str, Any], request_timeout: int) -> dict[str, Any]:
        self._raise_if_cancelled()
        response = None
        watcher_stop = threading.Event()
        started = time.monotonic()

        def cancel_watcher() -> None:
            while not watcher_stop.wait(0.05):
                if self.cancelled:
                    logger.warning("Ollama cancellation observed during request setup elapsed_ms=%.1f response_ready=%s", (time.monotonic() - started) * 1000, response is not None)
                    if response is not None:
                        self._hard_abort_response(response)
                        logger.warning("Ollama cancellation hard-abort finished elapsed_ms=%.1f", (time.monotonic() - started) * 1000)
                    return

        watcher = threading.Thread(target=cancel_watcher, name="ollama-cancel-watcher", daemon=True)
        watcher.start()
        try:
            streaming_payload = dict(payload)
            streaming_payload["stream"] = True
            logger.info("Ollama request start model=%s timeout=%s connect_timeout=%s", self.model, request_timeout, OLLAMA_CONNECT_TIMEOUT_SECONDS)
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=streaming_payload,
                timeout=(OLLAMA_CONNECT_TIMEOUT_SECONDS, request_timeout),
                stream=True,
            )
            response.raise_for_status()
            logger.info("Ollama response headers received elapsed_ms=%.1f cancelled=%s", (time.monotonic() - started) * 1000, self.cancelled)
            self._raise_if_cancelled()

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
            logger.info("Ollama stream loop exited elapsed_ms=%.1f cancelled=%s", (time.monotonic() - started) * 1000, self.cancelled)
            self._raise_if_cancelled()
            final_data["response"] = "".join(chunks)
            return final_data
        finally:
            watcher_stop.set()
            if response is not None:
                self._hard_abort_response(response)
            logger.info("Ollama request finished elapsed_ms=%.1f cancelled=%s", (time.monotonic() - started) * 1000, self.cancelled)

    def generate(self, prompt: str, timeout: int | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
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

        payload: dict[str, Any] = {"model": self.model, "prompt": prompt, "stream": False, "options": request_options}
        if agent_json:
            payload["format"] = "json"

        request_timeout = max(1, (timeout or self.timeout) - OLLAMA_TIMEOUT_MARGIN_SECONDS)
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
                data = self._generate_once({**payload, "prompt": correction}, request_timeout)
                raw = str(data.get("response", "")).strip()
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError("Ollama returned malformed JSON after corrective retry.") from exc
            if not isinstance(parsed, dict):
                raise ValueError("Ollama returned a JSON value, but the agent action must be an object.")

        return data
