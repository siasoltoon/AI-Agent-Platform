"""Deterministic orchestration boundary for professional autonomous missions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from agent_core.autonomous_developer import AutonomousDeveloper
from agent_core.checkpointed_runtime import CheckpointedRuntime
from agent_core.mission_contract import MissionContract
from agent_core.verification import verify_execution


class MissionPhase(str, Enum):
    CONTRACT = "contract"
    RECON = "recon"
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"
    ACCEPT = "accept"
    COMPLETE = "complete"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class MissionEvent:
    phase: MissionPhase
    status: str
    mission_id: str
    detail: str = ""


class MissionOrchestrator:
    """Own the mission lifecycle while delegating durable execution to AutonomousDeveloper."""

    def __init__(self, developer: AutonomousDeveloper, event_sink: Callable[[MissionEvent], None] | None = None):
        self.developer = developer
        self.event_sink = event_sink

    def _emit(self, event: MissionEvent) -> None:
        if self.event_sink is not None:
            self.event_sink(event)

    @staticmethod
    def contract(objective: str) -> MissionContract:
        return MissionContract.from_objective(objective)

    def _reconcile_interrupted_execution(self, mission_id: str) -> None:
        """Advance a task only when its persisted execution is independently verifiable."""
        memory = self.developer.memory_store.load(mission_id)
        if memory is None or not memory.active_task or not memory.active_execution_id:
            return
        result = memory.last_execution
        if not isinstance(result, dict):
            return
        if result.get("task_id") != memory.active_execution_id:
            return
        verification = verify_execution(result)
        if not verification.verified:
            return
        if memory.active_task not in memory.completed:
            memory.completed.append(memory.active_task)
        memory.pending = [item for item in memory.pending if item != memory.active_task]
        memory.checkpoint(
            step_id=memory.active_task,
            summary="reconciled previously committed execution after interruption",
            evidence={"execution_id": memory.active_execution_id, "verified": True, "reconciled": True},
        )
        memory.clear_execution()
        self.developer.memory_store.save(memory)

    def run(self, mission_id: str, objective: str, max_retries: int = 3) -> dict[str, Any]:
        contract = self.contract(objective)
        self._emit(MissionEvent(MissionPhase.CONTRACT, "completed", mission_id, str(contract.snapshot())))
        self._reconcile_interrupted_execution(mission_id)
        for phase in (MissionPhase.RECON, MissionPhase.PLAN, MissionPhase.EXECUTE):
            self._emit(MissionEvent(phase, "delegated", mission_id))

        original_runtime = self.developer.runtime
        self.developer.runtime = CheckpointedRuntime(
            original_runtime,
            self.developer.memory_store,
            mission_id,
        )
        try:
            result = self.developer.run(mission_id, objective, max_retries=max_retries)
        finally:
            self.developer.runtime = original_runtime
        status = str(result.get("status", "blocked"))
        terminal_phase = MissionPhase.COMPLETE if status == "completed" else MissionPhase.CANCELLED if status == "cancelled" else MissionPhase.BLOCKED
        self._emit(MissionEvent(MissionPhase.VERIFY, "completed" if result.get("verified") else "evaluated", mission_id))
        self._emit(MissionEvent(MissionPhase.ACCEPT, "accepted" if result.get("acceptance", {}).get("accepted") else "evaluated", mission_id))
        self._emit(MissionEvent(terminal_phase, status, mission_id))
        return {**result, "mission_contract": contract.snapshot()}

    def cancel(self, mission_id: str) -> dict[str, Any]:
        result = self.developer.cancel(mission_id)
        self._emit(MissionEvent(MissionPhase.CANCELLED, "cancelled", mission_id))
        return result
