"""Durable large-mission orchestration for autonomous software development.

The mission engine does not fake success. It turns a large request into
explicit milestones, persists progress through a supplied state store, and
only permits completion after the underlying execution path reports verified
evidence. The actual coding remains delegated to the existing AgentRuntime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class MissionStep:
    step_id: str
    title: str
    objective: str
    status: str = "pending"
    attempts: int = 0
    last_error: str | None = None
    result: dict[str, Any] | None = None


@dataclass
class MissionState:
    mission_id: str
    objective: str
    status: str = "planning"
    current_step: str | None = None
    steps: list[MissionStep] = field(default_factory=list)
    completed_steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)


class AutonomousMissionEngine:
    """Coordinate long-running developer missions without claiming unverified success."""

    MAX_STEPS = 64
    MAX_ATTEMPTS_PER_STEP = 3

    def __init__(self, runtime: Any, state_store: Any | None = None):
        self.runtime = runtime
        self.state_store = state_store

    def _persist(self, state: MissionState) -> None:
        if self.state_store is None:
            return
        payload = {
            "mission_id": state.mission_id,
            "objective": state.objective,
            "status": state.status,
            "current_step": state.current_step,
            "steps": [vars(step) for step in state.steps],
            "completed_steps": state.completed_steps,
            "failed_steps": state.failed_steps,
            "blockers": state.blockers,
            "verification": state.verification,
        }
        if hasattr(self.state_store, "save_mission"):
            self.state_store.save_mission(state.mission_id, payload)
        elif hasattr(self.state_store, "save"):
            self.state_store.save(state.mission_id, payload)

    @classmethod
    def build_steps(cls, objective: str) -> list[MissionStep]:
        """Create conservative developer milestones; the model still controls implementation details."""
        stages = [
            ("recon", "Repository reconnaissance", "Inspect the existing repository, architecture, dependencies, conventions, tests, and runtime constraints before changing code."),
            ("architecture", "Architecture and contract", "Define the implementation boundaries, interfaces, data flow, and compatibility constraints from the discovered repository state."),
            ("implementation", "Core implementation", "Implement the requested functionality incrementally, preserving working behavior and avoiding duplicate architecture."),
            ("integration", "Integration", "Connect the implementation to existing runtime, APIs, persistence, configuration, and user-facing surfaces where required."),
            ("testing", "Testing and diagnostics", "Run relevant tests and executable checks, diagnose failures, repair root causes, and repeat until the affected paths are healthy."),
            ("hardening", "Production hardening", "Handle validation, error paths, retries, timeouts, lifecycle behavior, security boundaries, and operational diagnostics relevant to the mission."),
            ("final_verification", "Final verification", "Reinspect changed behavior and require observable execution evidence before the mission can be marked completed."),
        ]
        return [MissionStep(step_id=key, title=title, objective=f"Mission: {objective}\n\n{detail}") for key, title, detail in stages]

    def start(self, mission_id: str, objective: str) -> MissionState:
        if not mission_id.strip() or not objective.strip():
            raise ValueError("mission_id and objective are required")
        state = MissionState(mission_id=mission_id.strip(), objective=objective.strip(), steps=self.build_steps(objective.strip()))
        self._persist(state)
        return state

    def run(self, state: MissionState, *, max_attempts: int = MAX_ATTEMPTS_PER_STEP) -> MissionState:
        attempts_limit = max(1, min(int(max_attempts), self.MAX_ATTEMPTS_PER_STEP))
        state.status = "running"
        self._persist(state)

        for step in state.steps:
            if step.status == "completed":
                continue
            state.current_step = step.step_id
            step.status = "running"
            self._persist(state)

            for _ in range(attempts_limit):
                step.attempts += 1
                try:
                    result = self.runtime.execute(
                        step.objective,
                        task_id=f"{state.mission_id}:{step.step_id}:{step.attempts}",
                        metadata={"mission_id": state.mission_id, "mission_step": step.step_id, "execution_profile": "large"},
                    )
                    step.result = result
                    evidence = result.get("result", {}).get("result", {}).get("execution_evidence", {})
                    if evidence.get("verified") is not True:
                        raise RuntimeError("Mission step returned without verified execution evidence")
                    step.status = "completed"
                    step.last_error = None
                    state.completed_steps.append(step.step_id)
                    self._persist(state)
                    break
                except Exception as exc:
                    step.last_error = f"{type(exc).__name__}: {exc}"
                    self._persist(state)
                    if step.attempts >= attempts_limit:
                        step.status = "blocked"
                        state.failed_steps.append(step.step_id)
                        state.blockers.append(step.last_error)
                        state.status = "blocked"
                        self._persist(state)
                        return state
            
        state.current_step = None
        state.status = "completed"
        state.verification = {"verified": True, "completed_steps": list(state.completed_steps), "step_count": len(state.steps)}
        self._persist(state)
        return state
