"""Large-task orchestration for multi-step local agent execution."""

from __future__ import annotations

import re
from typing import Any, Callable


class LargeTaskOrchestrator:
    """Turn a large instruction into bounded planning, execution and synthesis."""

    def __init__(
        self,
        generate: Callable[..., dict[str, Any]],
        threshold: int = 12000,
        max_steps: int = 12,
        max_retries: int = 1,
        context_chars: int = 12000,
        mission_context_chars: int = 28000,
        mission_chunk_chars: int = 16000,
    ):
        self.generate = generate
        self.threshold = threshold
        self.max_steps = max_steps
        self.max_retries = max(0, max_retries)
        self.context_chars = context_chars
        self.mission_context_chars = mission_context_chars
        self.mission_chunk_chars = mission_chunk_chars

    @staticmethod
    def _text(response: dict[str, Any]) -> str:
        return str(response.get("response", "")).strip()

    def _call_with_retry(self, prompt: str, timeout: int) -> dict[str, Any]:
        last_error: Exception | None = None
        for _attempt in range(self.max_retries + 1):
            try:
                return self.generate(prompt, timeout=timeout)
            except Exception as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    def _mission_context(self, prompt: str, timeout: int) -> str:
        if len(prompt) <= self.mission_context_chars:
            return prompt

        chunks = [
            prompt[i : i + self.mission_chunk_chars]
            for i in range(0, len(prompt), self.mission_chunk_chars)
        ]
        summaries: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            summary_prompt = f"""Extract the durable requirements, constraints,
interfaces, names, expected outputs, and important concrete details from this
part of a larger agent mission. Do not invent information. Keep technical
identifiers and code/API names exactly when present.

MISSION PART {index}/{len(chunks)}:
{chunk}
"""
            response = self._call_with_retry(summary_prompt, timeout)
            summaries.append(f"PART {index}:\n{self._text(response)}")

        return "\n\n".join(summaries)[: self.mission_context_chars]

    def _plan(self, mission: str, timeout: int) -> list[str]:
        planner_prompt = f"""You are the planning component of an AI agent.

Break the user's mission into a small sequence of concrete execution steps.
Do not solve the mission yet. Return ONLY a numbered list, one step per line.
Use at most {self.max_steps} steps. Each step must be independently actionable
and ordered so that later steps can use earlier results.

USER MISSION:
{mission}
"""
        response = self._call_with_retry(planner_prompt, timeout)
        text = self._text(response)
        steps: list[str] = []
        for line in text.splitlines():
            match = re.match(r"^\s*(?:\d+|[-*])\s*[.)-]?\s+(.+?)\s*$", line)
            if match:
                steps.append(match.group(1).strip())
        if not steps:
            steps = ["Complete the mission directly and return the requested result."]
        return steps[: self.max_steps]

    def execute(
        self,
        prompt: str,
        model: str,
        timeout: int,
    ) -> dict[str, Any]:
        if len(prompt) < self.threshold:
            response = self._call_with_retry(prompt, timeout)
            return {
                "mode": "single",
                "steps": 1,
                "result": self._text(response),
                "raw": response,
            }

        mission = self._mission_context(prompt, timeout)
        plan = self._plan(mission, timeout)
        completed: list[dict[str, Any]] = []
        shared_context = ""

        for index, step in enumerate(plan, start=1):
            step_prompt = f"""You are executing step {index} of a larger agent mission.

MISSION CONTEXT:
{mission}

EXECUTION PLAN:
{chr(10).join(f'{i}. {s}' for i, s in enumerate(plan, start=1))}

PREVIOUS EXECUTION CONTEXT:
{shared_context[-self.context_chars:]}

CURRENT STEP:
{step}

Complete this step carefully. Return the useful result of this step, not a
plan for a future step. Preserve concrete details that later steps may need.
"""
            try:
                response = self._call_with_retry(step_prompt, timeout)
                result = self._text(response)
                completed.append({
                    "step": index,
                    "instruction": step,
                    "status": "completed",
                    "result": result,
                })
                shared_context += f"\nSTEP {index} RESULT:\n{result}\n"
            except Exception as exc:
                completed.append({
                    "step": index,
                    "instruction": step,
                    "status": "failed",
                    "error": str(exc),
                })
                raise RuntimeError(
                    f"Large task failed at step {index}: {exc}"
                ) from exc

        synthesis_prompt = f"""You are the finalization component of an AI agent.

Produce the best final answer to the user's mission using the completed
execution results below. Do not mention internal orchestration unless it is
relevant to the requested result. Resolve inconsistencies using the mission
context as the source of truth.

MISSION CONTEXT:
{mission}

COMPLETED RESULTS:
{shared_context[-self.context_chars:]}
"""
        final_response = self._call_with_retry(synthesis_prompt, timeout)

        return {
            "mode": "multi_step",
            "steps": len(plan),
            "plan": plan,
            "execution": completed,
            "result": self._text(final_response),
            "raw": final_response,
        }
