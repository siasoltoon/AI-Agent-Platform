"""Integrated autonomous developer loop for large software missions."""

from __future__ import annotations

from typing import Any

from agent_core.acceptance import MissionAcceptanceGate
from agent_core.adaptive_planner import AdaptivePlanner
from agent_core.context_manager import MissionContextManager
from agent_core.mission_budget import MissionBudget, MissionBudgetState
from agent_core.mission_memory import MissionMemory, MissionMemoryStore
from agent_core.runtime import DEFAULT_LARGE_AGENT_STEPS
from agent_core.task_graph import GraphTask, TaskGraph
from agent_core.verification import FailureClass, classify_failure, verify_execution


class AutonomousDeveloper:
    """Run durable, bounded, adaptive developer missions over the existing AgentRuntime."""

    MAX_TASKS = 128

    def __init__(
        self,
        runtime: Any,
        memory_store: MissionMemoryStore | None = None,
        context: MissionContextManager | None = None,
        planner: AdaptivePlanner | None = None,
        acceptance: MissionAcceptanceGate | None = None,
        budget: MissionBudget | None = None,
    ):
        self.runtime = runtime
        self.memory_store = memory_store or MissionMemoryStore()
        self.context = context or MissionContextManager()
        self.planner = planner or AdaptivePlanner()
        self.acceptance = acceptance or MissionAcceptanceGate()
        self.budget = budget or MissionBudget(max_tasks=self.MAX_TASKS)

    @staticmethod
    def _initial_graph(objective: str) -> TaskGraph:
        tasks = [
            GraphTask("recon", "Repository reconnaissance", f"Inspect the repository, runtime, dependencies, tests, and conventions before changing anything. Mission: {objective}"),
            GraphTask("architecture", "Architecture", f"Derive architecture and implementation contracts from repository evidence. Mission: {objective}", {"recon"}),
            GraphTask("implementation", "Implementation", f"Implement the requested functionality incrementally using existing architecture. Mission: {objective}", {"architecture"}),
            GraphTask("integration", "Integration", f"Integrate affected components and preserve compatibility. Mission: {objective}", {"implementation"}),
            GraphTask("verification", "Testing and repair", f"Run relevant automated tests and executable checks, diagnose failures, repair root causes, and retest. Mission: {objective}", {"integration"}),
            GraphTask("hardening", "Production hardening", f"Harden validation, errors, retries, timeouts, lifecycle, security boundaries, and diagnostics relevant to the mission. Mission: {objective}", {"verification"}),
            GraphTask("acceptance", "Final acceptance", f"Review the final state and establish executable evidence for the requested behavior. Mission: {objective}", {"hardening"}),
        ]
        return TaskGraph(tasks)

    @staticmethod
    def _restore_graph(graph: TaskGraph, memory: MissionMemory) -> None:
        """Rehydrate graph state so a resumed mission never repeats completed work."""
        known = set(graph.tasks)
        completed = set(memory.completed)
        unknown = completed - known
        if unknown:
            raise ValueError(f"Persisted mission contains unknown completed tasks: {sorted(unknown)}")
        for task_id, task in graph.tasks.items():
            task.attempts = int(memory.task_attempts.get(task_id, 0))
            task.status = "completed" if task_id in completed else "pending"

    @staticmethod
    def _nested_execution(result: dict[str, Any]) -> dict[str, Any]:
        nested = result.get("result", {}).get("result", {}) if isinstance(result, dict) else {}
        return nested if isinstance(nested, dict) else {}

    @staticmethod
    def _root_task_id(task_id: str) -> str:
        for marker in (":diagnose:", ":repair:"):
            if marker in task_id:
                return task_id.split(marker, 1)[0]
        return task_id

    @staticmethod
    def _has_successful_test_evidence(result: dict[str, Any]) -> bool:
        records = result.get("tool_records", []) if isinstance(result, dict) else []
        if not isinstance(records, list):
            return False
        for record in records:
            if not isinstance(record, dict) or record.get("ok") is not True:
                continue
            tool = str(record.get("tool", "")).lower()
            payload = record.get("result") if isinstance(record.get("result"), dict) else {}
            command = str(payload.get("command", "")).lower()
            if tool in {"pytest", "test"} or "pytest" in command:
                return payload.get("code") == 0
            if "test" in command and any(token in command for token in ("python", "py", "npm", "yarn", "pnpm", "cargo", "go")):
                return payload.get("code") == 0
        return False

    @staticmethod
    def _budget_from_memory(memory: MissionMemory, configured: MissionBudget) -> MissionBudgetState:
        state = MissionBudgetState(configured)
        persisted = memory.mission_budget
        if isinstance(persisted, dict):
            state.steps = max(0, int(persisted.get("consumed_steps", 0)))
            state.tool_calls = max(0, int(persisted.get("consumed_tool_calls", 0)))
            state.output_chars = max(0, int(persisted.get("consumed_output_chars", 0)))
            state.recovery_attempts = max(0, int(persisted.get("consumed_recovery_attempts", 0)))
            state.tasks_started = max(0, int(persisted.get("tasks_started", 0)))
        return state

    def cancel(self, mission_id: str) -> dict[str, Any]:
        if not mission_id.strip():
            raise ValueError("mission_id is required")
        memory = self.memory_store.load(mission_id)
        if memory is None:
            raise ValueError(f"Unknown mission: {mission_id}")
        if memory.status == "completed":
            return {"mission_id": mission_id, "status": "completed", "cancelled": False, "memory": memory.snapshot()}
        if memory.status == "cancelled":
            return {"mission_id": mission_id, "status": "cancelled", "cancelled": True, "memory": memory.snapshot()}
        memory.transition("cancelled")
        self.memory_store.save(memory)
        return {"mission_id": mission_id, "status": "cancelled", "cancelled": True, "memory": memory.snapshot()}

    def _cancelled_snapshot(self, mission_id: str) -> dict[str, Any] | None:
        latest = self.memory_store.load(mission_id)
        if latest is not None and latest.status == "cancelled":
            return {"mission_id": mission_id, "status": "cancelled", "cancelled": True, "memory": latest.snapshot()}
        return None

    def _recover(self, graph: TaskGraph, task: GraphTask, error: BaseException | str, memory: MissionMemory, budget: MissionBudgetState) -> bool:
        action = self.planner.recovery_action(error)
        category = classify_failure(error)
        memory.record_failure(task.task_id, f"{category.value}: {error}; action={action}")
        if action in {"diagnose_and_repair", "inspect_tool_and_retry_or_switch_tool"}:
            if budget.recovery_attempts >= budget.budget.max_recovery_attempts:
                return False
            budget.record_recovery()
            repairs = self.planner.expand_after_failure(graph, task.task_id, error)
            if repairs:
                memory.checkpoint(step_id=task.task_id, summary="scheduled bounded diagnosis and repair before retry", evidence={"repair_tasks": [repair.task_id for repair in repairs], "budget": budget.snapshot()})
                return True
        return False

    def _blocked_budget(self, memory: MissionMemory, budget: MissionBudgetState, reason: str) -> dict[str, Any]:
        memory.mission_budget = budget.snapshot()
        memory.checkpoint(step_id="budget", summary="mission stopped by deterministic resource governance", evidence={"reason": reason, "budget": memory.mission_budget})
        memory.transition("blocked")
        self.memory_store.save(memory)
        return {"mission_id": memory.mission_id, "status": "blocked", "failure_class": "budget", "reason": reason, "memory": memory.snapshot()}

    def run(self, mission_id: str, objective: str, max_retries: int = 3) -> dict[str, Any]:
        if not mission_id.strip() or not objective.strip():
            raise ValueError("mission_id and objective are required")
        retries = max(1, min(int(max_retries), 5))
        objective = objective.strip()
        memory = self.memory_store.load(mission_id)
        if memory is None:
            memory = MissionMemory(mission_id, objective)
        elif memory.objective.strip() != objective:
            raise ValueError("A persisted mission cannot be resumed with a different objective.")

        if memory.status == "completed":
            return {"mission_id": mission_id, "status": "completed", "verified": True, "completed_tasks": list(memory.completed), "memory": memory.snapshot()}
        if memory.status == "cancelled":
            return {"mission_id": mission_id, "status": "cancelled", "memory": memory.snapshot()}
        memory.transition("running")
        budget = self._budget_from_memory(memory, self.budget)

        graph = self._initial_graph(objective)
        self._restore_graph(graph, memory)
        memory.pending = [task.task_id for task in graph.tasks.values() if task.status != "completed"]
        memory.mission_budget = budget.snapshot()
        self.memory_store.save(memory)

        while not graph.is_complete():
            cancelled = self._cancelled_snapshot(mission_id)
            if cancelled:
                return cancelled
            reason = budget.reason()
            if reason:
                return self._blocked_budget(memory, budget, reason)
            ready = graph.ready()
            if not ready:
                blockers = [task.task_id for task in graph.tasks.values() if task.status == "blocked"]
                memory.transition("blocked")
                memory.mission_budget = budget.snapshot()
                self.memory_store.save(memory)
                return {"mission_id": mission_id, "status": "blocked", "blockers": blockers, "memory": memory.snapshot()}

            for task in list(ready):
                cancelled = self._cancelled_snapshot(mission_id)
                if cancelled:
                    return cancelled
                if task.attempts == 0:
                    reason = budget.before_task()
                    if reason:
                        return self._blocked_budget(memory, budget, reason)
                completed = False
                starting_attempt = memory.task_attempts.get(task.task_id, 0)
                for offset in range(1, retries + 1):
                    cancelled = self._cancelled_snapshot(mission_id)
                    if cancelled:
                        return cancelled
                    reason = budget.reason()
                    if reason:
                        return self._blocked_budget(memory, budget, reason)
                    attempt = starting_attempt + offset
                    task.attempts = attempt
                    memory.record_attempt(task.task_id, attempt)
                    recent = [f"{item['step_id']}: {item['summary']}" for item in memory.checkpoints[-8:]]
                    prompt = self.context.build(objective=objective, architecture=memory.architecture, active_task=task.objective, memory=str(memory.snapshot()), recent_results=recent)
                    limits = budget.execution_limits()
                    memory.checkpoint(step_id=task.task_id, summary=f"attempt {attempt}", evidence={"budget": budget.snapshot(), "execution_limits": limits})
                    self.memory_store.save(memory)
                    try:
                        result = self.runtime.execute(
                            prompt,
                            task_id=f"{mission_id}:{task.task_id}:{attempt}",
                            timeout_seconds=limits["timeout_seconds"],
                            metadata={
                                "mission_id": mission_id,
                                "mission_task": task.task_id,
                                "max_agent_steps": limits["max_agent_steps"],
                                "max_output_chars": limits["max_output_chars"],
                                "execution_profile": "large",
                                "mission_budget": budget.snapshot(),
                            },
                        )
                        cancelled = self._cancelled_snapshot(mission_id)
                        if cancelled:
                            return cancelled
                        nested = self._nested_execution(result)
                        memory.record_execution(nested)
                        evidence = nested.get("execution_evidence", {}) if isinstance(nested, dict) else {}
                        if isinstance(evidence, dict):
                            budget.record_execution(evidence)
                        reason = budget.reason()
                        memory.mission_budget = budget.snapshot()
                        verification = verify_execution(nested)
                        if not verification.verified:
                            raise RuntimeError(f"verification failed: {verification.blockers}")
                        if reason:
                            return self._blocked_budget(memory, budget, reason)

                        graph.mark_completed(task.task_id)
                        if task.task_id not in memory.completed:
                            memory.completed.append(task.task_id)
                        if task.task_id == "verification":
                            memory.record_test("mission verification", self._has_successful_test_evidence(nested), "derived from the actual successful test command in runtime evidence")
                        memory.pending = [t.task_id for t in graph.tasks.values() if t.status != "completed"]
                        memory.checkpoint(step_id=task.task_id, summary="completed with verified evidence", evidence=verification.checks)
                        self.memory_store.save(memory)
                        completed = True
                        break
                    except Exception as exc:
                        category = classify_failure(exc)
                        repaired = False
                        if offset == retries and category not in {FailureClass.BLOCKING, FailureClass.VALIDATION, FailureClass.UNKNOWN}:
                            repaired = self._recover(graph, task, exc, memory, budget)
                        else:
                            memory.record_failure(task.task_id, f"{category.value}: {exc}")
                        memory.mission_budget = budget.snapshot()
                        self.memory_store.save(memory)
                        if repaired:
                            graph.mark_pending(task.task_id)
                            memory.pending = [t.task_id for t in graph.tasks.values() if t.status != "completed"]
                            self.memory_store.save(memory)
                            break
                        if category is FailureClass.BLOCKING or offset == retries:
                            graph.mark_blocked(task.task_id)
                            memory.pending = [t.task_id for t in graph.tasks.values() if t.status != "completed"]
                            memory.transition("blocked")
                            self.memory_store.save(memory)
                            return {"mission_id": mission_id, "status": "blocked", "task": self._root_task_id(task.task_id), "failure_class": category.value, "error": str(exc), "memory": memory.snapshot()}
                if not completed and graph.tasks[task.task_id].status == "pending":
                    continue
                if not completed:
                    memory.transition("blocked")
                    self.memory_store.save(memory)
                    return {"mission_id": mission_id, "status": "blocked", "task": self._root_task_id(task.task_id), "memory": memory.snapshot()}

        last_execution = memory.last_execution
        final_verification = verify_execution(last_execution)
        tests_checked = any(item.get("passed") is True for item in memory.tests)
        gate = self.acceptance.evaluate(mission_status="completed", plan_complete=graph.is_complete(), tests_checked=tests_checked, final_reviewed="acceptance" in memory.completed, execution_result=last_execution if final_verification.verified else None)
        if not gate.accepted:
            memory.transition("blocked")
            memory.mission_budget = budget.snapshot()
            self.memory_store.save(memory)
            return {"mission_id": mission_id, "status": "blocked", "reasons": gate.reasons, "memory": memory.snapshot()}
        memory.pending = []
        memory.mission_budget = budget.snapshot()
        memory.transition("completed")
        self.memory_store.save(memory)
        return {"mission_id": mission_id, "status": "completed", "verified": True, "completed_tasks": list(memory.completed), "memory": memory.snapshot(), "acceptance": {"accepted": True, "checks": gate.verification.checks}}
