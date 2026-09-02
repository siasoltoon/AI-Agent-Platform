"""Adaptive planning primitives for large autonomous software missions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_core.task_graph import GraphTask, TaskGraph
from agent_core.verification import FailureClass, classify_failure


@dataclass
class PlanningContext:
    objective: str
    repository_summary: str = ""
    constraints: list[str] = field(default_factory=list)
    discovered_components: list[str] = field(default_factory=list)
    known_failures: list[str] = field(default_factory=list)


class AdaptivePlanner:
    """Build and evolve a bounded task graph from repository evidence."""

    MAX_TASKS = 128

    def build_graph(self, context: PlanningContext, proposed_tasks: list[dict[str, Any]]) -> TaskGraph:
        if not context.objective.strip():
            raise ValueError("Planning objective cannot be empty")
        if not proposed_tasks:
            raise ValueError("Planner requires at least one proposed task")
        if len(proposed_tasks) > self.MAX_TASKS:
            raise ValueError(f"Planner cannot create more than {self.MAX_TASKS} tasks")
        tasks = []
        seen: set[str] = set()
        for item in proposed_tasks:
            task_id = str(item.get("task_id", "")).strip()
            title = str(item.get("title", "")).strip()
            objective = str(item.get("objective", "")).strip()
            deps = {str(dep).strip() for dep in item.get("depends_on", []) if str(dep).strip()}
            if not task_id or not title or not objective:
                raise ValueError("Every planned task requires task_id, title, and objective")
            if task_id in seen:
                raise ValueError(f"Duplicate planned task: {task_id}")
            seen.add(task_id)
            tasks.append(GraphTask(task_id, title, objective, deps))
        return TaskGraph(tasks)

    def recovery_action(self, error: BaseException | str) -> str:
        category = classify_failure(error)
        return {
            FailureClass.TRANSIENT: "retry_with_backoff",
            FailureClass.TEST_FAILURE: "diagnose_and_repair",
            FailureClass.VALIDATION: "inspect_contract_and_correct_input",
            FailureClass.TOOL_FAILURE: "inspect_tool_and_retry_or_switch_tool",
            FailureClass.ENVIRONMENT: "repair_environment_or_mark_blocked_with_evidence",
            FailureClass.BLOCKING: "stop_and_report_evidence",
            FailureClass.UNKNOWN: "inspect_failure_evidence_before_retry",
        }[category]

    @staticmethod
    def _is_recovery_task(task_id: str) -> bool:
        """Recovery work is deliberately terminal for adaptive expansion.

        Diagnosis/repair tasks may be retried by the normal bounded retry loop,
        but a failure inside recovery work must not recursively create another
        diagnosis/repair chain. This preserves the graph bound and guarantees
        that an unrecoverable recovery path eventually becomes blocked instead
        of consuming the entire task budget.
        """
        parts = task_id.split(":")
        return "diagnose" in parts or "repair" in parts

    def expand_after_failure(
        self,
        graph: TaskGraph,
        failed_task_id: str,
        error: BaseException | str,
    ) -> list[GraphTask]:
        """Add bounded diagnosis/repair work that must complete before retry.

        Only original mission tasks may spawn recovery work. Recovery tasks can
        still be retried by the caller, but never recursively expanded.
        """
        if failed_task_id not in graph.tasks:
            raise KeyError(failed_task_id)
        if self._is_recovery_task(failed_task_id):
            return []

        category = classify_failure(error)
        if category in {FailureClass.BLOCKING, FailureClass.VALIDATION}:
            return []

        attempt = graph.tasks[failed_task_id].attempts + 1
        diagnosis_id = f"{failed_task_id}:diagnose:{attempt}"
        repair_id = f"{failed_task_id}:repair:{attempt}"
        if diagnosis_id in graph.tasks or repair_id in graph.tasks:
            return []
        if len(graph.tasks) + 2 > self.MAX_TASKS:
            return []

        original = graph.tasks[failed_task_id]
        diagnosis = GraphTask(
            diagnosis_id,
            "Diagnose failure",
            f"Inspect the failure evidence for task {failed_task_id}, identify the root cause, and determine the minimal repair.",
            set(original.depends_on),
        )
        graph.add_task(diagnosis)
        try:
            repair = GraphTask(
                repair_id,
                "Repair root cause",
                f"Apply and verify the root-cause repair for task {failed_task_id} after diagnosis.",
                {diagnosis_id},
            )
            graph.add_task(repair)
            graph.add_dependency(failed_task_id, repair_id)
        except Exception:
            graph.tasks.pop(diagnosis_id, None)
            raise
        return [diagnosis, repair]
