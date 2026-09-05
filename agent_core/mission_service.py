"""Production mission service that connects task dispatch to the durable mission orchestrator."""

from __future__ import annotations

from typing import Any

from agent_core.autonomous_developer import AutonomousDeveloper
from agent_core.mission_orchestrator import MissionOrchestrator
from agent_core.runtime import AgentRuntime


class MissionService:
    """Expose the professional mission lifecycle through the existing task command path."""

    def __init__(self, runtime: AgentRuntime | None = None, event_sink=None) -> None:
        self.runtime = runtime or AgentRuntime()
        self.developer = AutonomousDeveloper(self.runtime)
        self.orchestrator = MissionOrchestrator(self.developer, event_sink=event_sink)

    def execute(
        self,
        prompt: str,
        *,
        task_id: str,
        model: str | None = None,
        timeout_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a mission while preserving the Task API's execution envelope."""
        mission_metadata = dict(metadata or {})
        contract = self.orchestrator.contract(prompt)
        mission_metadata.update({
            "mission_mode": "professional",
            "mission_contract": contract.snapshot(),
            "network_access": contract.network_access,
        })
        result = self.orchestrator.run(
            task_id,
            prompt,
            max_retries=int(mission_metadata.get("max_retries", 3)),
            model=model,
            timeout_seconds=timeout_seconds,
            metadata=mission_metadata,
        )
        result["execution_mode"] = "professional_mission"
        result["model"] = model or self.runtime.default_model
        result["metadata"] = mission_metadata
        return result

    def cancel(self, task_id: str) -> dict[str, Any]:
        return self.orchestrator.cancel(task_id)
