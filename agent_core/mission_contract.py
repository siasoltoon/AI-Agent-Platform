"""Deterministic mission requirements used by autonomous acceptance gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re


@dataclass(frozen=True)
class MissionContract:
    """Machine-readable acceptance requirements derived from a mission objective.

    The contract deliberately uses conservative heuristics: ambiguous objectives
    keep the stronger requirement instead of silently accepting less evidence.
    """

    objective: str
    read_only: bool
    requires_tests: bool
    requires_build: bool
    requires_inspection: bool = True
    requires_final_review: bool = True
    requires_execution_evidence: bool = True

    @classmethod
    def from_objective(cls, objective: str) -> "MissionContract":
        text = str(objective or "").strip()
        if not text:
            raise ValueError("Mission objective cannot be empty")
        lower = text.lower()

        read_only = bool(re.search(
            r"\bread[- ]only\b|\bdo not (?:modify|change|write|delete|create)\b|"
            r"\bwithout making changes\b|\bmake no changes\b|\binspect(?:ion)? only\b|"
            r"\bdo not alter (?:the )?(?:workspace|repository|files?)\b",
            lower,
        ))

        docs_only = bool(re.search(
            r"\b(?:documentation|readme|docs?)\b.*\bonly\b|\bonly\b.*\b(?:documentation|readme|docs?)\b",
            lower,
        ))
        inspection = bool(re.search(r"\b(?:inspect|inspection|audit|review)\b", lower))
        implementation = bool(re.search(
            r"\b(?:implement|implementation|modify|change|fix|repair|refactor|create|add|remove|delete|build|develop|code|feature|bug)\b",
            lower,
        ))
        explicit_tests = bool(re.search(
            r"\b(?:test|tests|pytest|unit tests|integration tests|e2e|end[- ]to[- ]end|test suite|validate|verification)\b",
            lower,
        ))
        build = bool(re.search(
            r"\b(?:build|compile|compilation|package|bundle|npm run build|production build|release)\b",
            lower,
        ))

        requires_tests = explicit_tests or (implementation and not docs_only and not read_only)
        requires_build = build and not read_only

        return cls(
            objective=text,
            read_only=read_only,
            requires_tests=requires_tests,
            requires_build=requires_build,
            requires_inspection=inspection or implementation or not read_only,
        )

    def snapshot(self) -> dict[str, object]:
        return asdict(self)
