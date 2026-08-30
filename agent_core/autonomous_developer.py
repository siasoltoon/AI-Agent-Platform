"""Integrated autonomous developer loop for large software missions."""

from __future__ import annotations

from typing import Any

from agent_core.context_manager import MissionContextManager
from agent_core.mission_memory import MissionMemory, MissionMemoryStore
from agent_core.task_graph import GraphTask, TaskGraph
from agent_core.verification import classify_failure, verify_execution, FailureClass


class AutonomousDeveloper:
    """Run a durable developer mission over the existing AgentRuntime.

    The planner is intentionally deterministic at this boundary: it creates
    safe foundation milestones, while AgentExecutor remains responsible for
    actual repository inspection, coding, commands, tests, and evidence.
    """

    def __init__(self, runtime: Any, memory_store: MissionMemoryStore | None = None,
                 context: MissionContextManager | None = None):
        self.runtime = runtime
        self.memory_store = memory_store or MissionMemoryStore()
        self.context = context or MissionContextManager()

    @staticmethod
    def _graph(objective: str) -> TaskGraph:
        tasks = [
            GraphTask("recon", "Repository reconnaissance", f"Inspect the repository and runtime before changing anything. Mission: {objective}"),
            GraphTask("architecture", "Architecture", f"Derive architecture and implementation contracts from the inspected repository. Mission: {objective}", {"recon"}),
            GraphTask("implementation", "Implementation", f"Implement the mission incrementally using existing architecture. Mission: {objective}", {"architecture"}),
            GraphTask("integration", "Integration", f"Integrate all affected components and preserve compatibility. Mission: {objective}", {"implementation"}),
            GraphTask("verification", "Testing and repair", f"Run relevant checks, diagnose failures, repair root causes, and retest. Mission: {objective}", {"integration"}),
            GraphTask("hardening", "Production hardening", f"Harden validation, errors, retries, timeouts, lifecycle, and diagnostics. Mission: {objective}", {"verification"}),
            GraphTask("acceptance", "Final acceptance", f"Review the final state and establish executable evidence for the requested behavior. Mission: {objective}", {"hardening"}),
        ]
        return TaskGraph(tasks)

    def run(self, mission_id: str, objective: str, max_retries: int = 3) -> dict[str, Any]:
        if not mission_id.strip() or not objective.strip():
            raise ValueError("mission_id and objective are required")
        retries = max(1, min(int(max_retries), 5))
        memory = self.memory_store.load(mission_id) or MissionMemory(mission_id, objective.strip())
        graph = self._graph(objective.strip())
        memory.pending = [task.task_id for task in graph.tasks.values()]
        self.memory_store.save(memory)

        while not graph.is_complete():
            ready = graph.ready()
            if not ready:
                blockers = [task.task_id for task in graph.tasks.values() if task.status == "blocked"]
                raise RuntimeError(f"Mission blocked; unresolved task dependencies: {blockers}")
            for task in ready:
                success = False
                for attempt in range(1, retries + 1):
                    graph.tasks[task.task_id].attempts = attempt
                    memory.checkpoint(step_id=task.task_id, summary=f"starting attempt {attempt}")
                    self.memory_store.save(memory)
                    recent = [f"{item['step_id']}: {item['summary']}" for item in memory.checkpoints[-6:]]
                    prompt = self.context.build(objective=objective, architecture=memory.architecture,
                                                active_task=task.objective, memory=str(memory.snapshot()), recent_results=recent)
                    try:
                        result = self.runtime.execute(prompt, task_id=f"{mission_id}:{task.task_id}:{attempt}",
                                                     metadata={"mission_id": mission_id, "mission_task": task.task_id,
                                                               "max_agent_steps": 64, "execution_profile": "large"})
                        nested = result.get("result", {}).get("result", {})
                        verification = verify_execution(nested)
                        if not verification.verified:
                            raise RuntimeError(f"verification failed: {verification.blockers}")
                        graph.mark_completed(task.task_id)
                        memory.completed.append(task.task_id)
                        memory.pending = [t.task_id for t in graph.tasks.values() if t.status != "completed"]
                        memory.checkpoint(step_id=task.task_id, summary="completed with verified evidence", evidence=verification.checks)
                        self.memory_store.save(memory)
                        success = True
                        break
                    except Exception as exc:
                        failure = classify_failure(exc)
                        memory.record_failure(task.task_id, f"{failure.value}: {exc}")
                        self.memory_store.save(memory)
                        if failure is FailureClass.BLOCKING or attempt == retries:
                            graph.mark_blocked(task.task_id)
                            return {"mission_id": mission_id, "status": "blocked", "task": task.task_id,
                                    "failure_class": failure.value, "error": str(exc), "memory": memory.snapshot()}
                if not success:
                    graph.mark_blocked(task.task_id)
                    return {"mission_id": mission_id, "status": "blocked", "task": task.task_id, "memory": memory.snapshot()}

        return {"mission_id": mission_id, "status": "completed", "verified": True,
                "completed_tasks": list(memory.completed), "memory": memory.snapshot()}
