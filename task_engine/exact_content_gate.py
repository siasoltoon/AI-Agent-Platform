"""Deterministic exact-content acceptance checks for task completion."""

from __future__ import annotations

import re
from typing import Any

_FILE_RE = re.compile(r"(?<![\w/])(?:[\w.-]+/)*[\w.-]+\.[A-Za-z0-9]{1,12}(?![\w])")
_EXACT_MARKER_RE = re.compile(
    r"(?:with|must\s+contain|must\s+have|should\s+contain|should\s+have|has\s+to\s+contain|has\s+to\s+have|contain|contents?\s+(?:must|should)\s+be)"
    r"\s+(?:exactly\s+)?(?:these\s+\w+\s+lines?\s*:\s*|the\s+exact\s+(?:content|contents)\s*:\s*|exact(?:ly)?\s*(?:content|contents)?\s*:\s*|:\s*)",
    re.IGNORECASE,
)
_BOUNDARY_RE = re.compile(
    r"(?:\n\s*|(?<=\.)\s+|\s+)(?:after\s+creating|after\s+it|then\s+(?:directly\s+)?(?:read|verify|check|confirm)|do\s+not\b|please\s+|once\s+|when\s+finished|verification\s+rules?|constraints?:?)\b",
    re.IGNORECASE,
)


def requested_paths(prompt: str) -> set[str]:
    return {path.replace("\\", "/").lower().lstrip("./") for path in _FILE_RE.findall(str(prompt))}


def _clean_payload(payload: str) -> str:
    value = payload.strip()
    if value.startswith("```"):
        first_newline = value.find("\n")
        if first_newline >= 0:
            value = value[first_newline + 1 :]
        if value.endswith("```"):
            value = value[:-3]
        value = value.rstrip("\n")
    return value


def extract_exact_content_requirements(prompt: str) -> dict[str, str]:
    """Extract explicit exact-content requirements without asking the model."""
    text = str(prompt)
    paths = requested_paths(text)
    requirements: dict[str, str] = {}
    for path in paths:
        path_pos = text.lower().find(path.lower())
        if path_pos < 0:
            continue
        tail = text[path_pos + len(path) :]
        marker = _EXACT_MARKER_RE.search(tail)
        if not marker:
            continue
        payload = tail[marker.end() :]
        boundary = _BOUNDARY_RE.search(payload)
        if boundary:
            payload = payload[: boundary.start()]
        payload = _clean_payload(payload)
        if payload:
            requirements[path] = payload
    return requirements


def has_exact_content_requirement(prompt: str) -> bool:
    lower = str(prompt).lower()
    return "exactly" in lower and bool(_FILE_RE.search(str(prompt)))


def verify_exact_content(prompt: str, evidence: dict[str, Any]) -> dict[str, Any]:
    """Verify requested content against independently read filesystem evidence."""
    if not has_exact_content_requirement(prompt):
        return {"exact_content_verified": False, "exact_content_required": False, "exact_content_blockers": []}

    requirements = extract_exact_content_requirements(prompt)
    if not requirements:
        return {"exact_content_verified": False, "exact_content_required": True, "exact_content_blockers": ["exact_content_requirement_unparseable"]}

    checks = evidence.get("checks") if isinstance(evidence, dict) else None
    if not isinstance(checks, list):
        return {"exact_content_verified": False, "exact_content_required": True, "exact_content_blockers": ["missing_execution_checks"]}

    blockers: list[str] = []
    for path, expected in requirements.items():
        matching = [
            check for check in checks
            if isinstance(check, dict)
            and str(check.get("path", "")).replace("\\", "/").lower().lstrip("./") == path
        ]
        write_check = next((c for c in matching if c.get("type") == "file_content_matches_write"), None)
        read_check = next((c for c in matching if c.get("type") == "read_content_matches_write"), None)
        read_exists = next((c for c in matching if c.get("type") == "read_verified_exists"), None)

        if not write_check or write_check.get("passed") is not True:
            blockers.append(f"write_content_not_verified:{path}")
        elif write_check.get("expected_content") != expected:
            blockers.append(f"requested_content_differs_from_write:{path}")

        if not read_exists or read_exists.get("passed") is not True:
            blockers.append(f"direct_read_missing:{path}")
        if not read_check or read_check.get("passed") is not True:
            blockers.append(f"read_content_not_verified:{path}")
        elif read_check.get("actual_content") != expected:
            blockers.append(f"requested_content_differs_from_read:{path}")

    return {
        "exact_content_verified": not blockers,
        "exact_content_required": True,
        "exact_content_paths": sorted(requirements),
        "exact_content_blockers": blockers,
    }
