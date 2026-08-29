"""Reliable large-task orchestration for local agent execution.

The orchestrator keeps the original mission intact while using bounded model
calls for planning, execution and finalization. It is dependency free so it
can run on the local worker architecture.
"""

from __future__ import annotations

import re
from typing import Any, Callable


class LargeTaskOrchestrator:
    """Plan, execute, validate and synthesize large missions safely."""

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
        self.threshold = max(1, threshold)
        self.max_steps = max(1, max_steps)
        self.max_retries = max(0, max_retries)
        self.context_chars = max(1000, context_chars)
        self.mission_context_chars = max(self.context_chars, mission_context_chars)
        self.mission_chunk_chars = max(1000, mission_chunk_chars)

    @staticmethod
    def _text(response: dict[str, Any]) -> str:
        value = response.get("response", "")
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    @staticmethod
    def _clip(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        head = max(1, limit * 2 // 3)
        tail = max(1, limit - head)
        return f"{text[:head]}\n\n...[content clipped]...\n\n{text[-tail:]}"

    def _call_with_retry(self, prompt: str, timeout: int) -> dict[str, Any]:
        last_error: Exception | None = None
        for _attempt in range(self.max_retries + 1):
            try:
                response = self.generate(prompt, timeout=timeout)
                if not isinstance(response, dict):
                    raise RuntimeError("Worker returned an invalid response object.")
                return response
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
            summary_prompt = f"""Extract durable requirements from this part of a larger agent mission.
Preserve technical identifiers, filenames, APIs, commands, constraints,
acceptance criteria and exact requested outputs. Do not invent information.
Return concise factual notes only.

MISSION PART {index}/{len(chunks)}:
{chunk}
"""
            response = self._call_with_retry(summary_prompt, timeout)
            summary = self._text(response)
            if not summary:
                raise RuntimeError(
                    f"Mission-context summarization returned empty output for part {index}."
                )
            summaries.append(f"PART {index}:\n{summary}")

        return self._clip("\n\n".join(summaries), self.mission_context_chars)

    def _plan(self, mission: str, timeout: int) -> list[str]:
        planner_prompt = f"""You are the planning component of an AI agent.

Break the user's mission into a small ordered sequence of concrete execution
steps. Do not solve the mission. Return ONLY a numbered list, one actionable
step per line. Use at most {self.max_steps} steps. Avoid vague steps such as
'continue' or 'do everything'.

USER MISSION:
{mission}
"""
        response = self._call_with_retry(planner_prompt, timeout)
        text = self._text(response)
        steps: list[str] = []
        seen: set[str] = set()
        for line in text.splitlines():
            match = re.match(r"^\s*(?:\d+|[-*])\s*[.)-]?\s+(.+?)\s*$", line)
            if match:
                step = match.group(1).strip()
                key = step.casefold()
                if step and key not in seen:
                    steps.append(step)
                    seen.add(key)
        if not steps:
            steps = ["Complete the mission directly and return the requested result."]
        return steps[: self.max_steps]

    @staticmethod
    def _validate_result(result: str, index: int) -> None:
        if not result:
            raise RuntimeError(f"Step {index} returned an empty result.")

    def execute(self, prompt: str, model: str, timeout: int) -> dict[str, Any]:
        if not prompt or not prompt.strip():
            raise ValueError("Large-task prompt cannot be empty.")

        prompt = prompt.strip()
        if len(prompt) < self.threshold:
            response = self._call_with_retry(prompt, timeout)
            result = self._text(response)
            self._validate_result(result, 1)
            return {"mode": "single", "steps": 1, "result": result, "raw": response}

        mission = self._mission_context(prompt, timeout)
        plan = self._plan(mission, timeout)
        completed: list[dict[str, Any]] = []
        shared_context = ""

        for index, step in enumerate(plan, start=1):
            previous = self._clip(shared_context, self.context_chars)
            step_prompt = f"""You are executing step {index} of a larger agent mission.

MISSION CONTEXT:
{mission}

EXECUTION PLAN:
{chr(10).join(f'{i}. {s}' for i, s in enumerate(plan, start=1))}

PREVIOUS EXECUTION CONTEXT:
{previous or '(none)'}

CURRENT STEP:
{step}

Complete this step now. Return the useful result of this step, not a plan for
a future step. Preserve concrete details needed by later steps.
"""
            try:
                response = self._call_with_retry(step_prompt, timeout)
                result = self._text(response)
                self._validate_result(result, index)
                completed.append({
                    "step": index,
                    "instruction": step,
                    "status": "completed",
                    "result": result,
                })
                shared_context += f"\nSTEP {index} RESULT:\n{result}\n"
                shared_context = self._clip(shared_context, self.mission_context_chars)
            except Exception as exc:
                completed.append({
                    "step": index,
                    "instruction": step,
                    "status": "failed",
                    "error": str(exc),
                })
                raise RuntimeError(f"Large task failed at step {index}: {exc}") from exc

        synthesis_prompt = f"""You are the finalization component of an AI agent.

Produce the best final answer to the user's mission using the execution
results below. Do not mention internal orchestration unless relevant. Treat
the mission context as the source of truth and do not invent missing facts.
If an execution result conflicts with the mission, follow the mission and
clearly correct the conflicting result.

MISSION CONTEXT:
{mission}

COMPLETED EXECUTION RESULTS:
{self._clip(shared_context, self.mission_context_chars)}
"""
        final_response = self._call_with_retry(synthesis_prompt, timeout)
        final_text = self._text(final_response)
        self._validate_result(final_text, 0)

        return {
            "mode": "multi_step",
            "steps": len(plan),
            "plan": plan,
            "execution": completed,
            "result": final_text,
            "raw": final_response,
        }
