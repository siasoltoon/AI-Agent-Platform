from __future__ import annotations

import json
import re
from typing import Any


class ActionParseError(ValueError):
    """Raised when a model response cannot be parsed as an action."""


class ActionParser:
    """Parse common LLM JSON action formats robustly."""

    _FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)

    @classmethod
    def extract_object(cls, text: str) -> dict[str, Any]:
        raw = str(text or "").strip()
        if not raw:
            raise ActionParseError("Model returned an empty response.")
        candidates = [raw]
        candidates.extend(m.group(1).strip() for m in cls._FENCE_RE.finditer(raw))
        for candidate in candidates:
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                value = cls._scan_objects(candidate)
            if isinstance(value, dict):
                return value
        raise ActionParseError("Model did not return a valid JSON action.")

    @staticmethod
    def _scan_objects(text: str) -> dict[str, Any] | None:
        for start, char in enumerate(text):
            if char != "{":
                continue
            depth = 0
            in_string = False
            escaped = False
            for index in range(start, len(text)):
                char = text[index]
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            value = json.loads(text[start:index + 1])
                        except json.JSONDecodeError:
                            break
                        if isinstance(value, dict):
                            return value
                        break
        return None

    @staticmethod
    def normalize(decision: dict[str, Any], tools: set[str], aliases: set[str]) -> dict[str, Any]:
        action = str(decision.get("action", "")).strip().lower()
        tool = str(decision.get("tool", "")).strip().lower()
        if action in tools or action in aliases:
            return {**decision, "action": "tool", "tool": tool or action}
        if tool in tools or tool in aliases:
            return {**decision, "action": "tool", "tool": tool}
        return decision
