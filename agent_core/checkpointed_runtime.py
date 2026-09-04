"""Runtime adapter that persists execution identity around external work."""

from __future__ import annotations

from typing import Any

from agent_core.verification import verify_execution


class CheckpointedRuntime:
    """Persist an active execution before delegation and commit verified results after it returns."""

    def __init__(self, runtime: Any, memory_store: Any, mission_id: str):
        self.runtime = runtime
        self.memory_store = memory_store
        self.mission_id = mission_id

    @staticmethod
    def _nested_execution(result: dict[str, Any]) -> dict[str, Any]:
        nested = result.get("result", {}).get("result", {}) if isinstance(result, dict) else {}
        return nested if isinstance(nested, dict) else {}

    def _graph_task_id(self, execution_id: str) -> str:
        prefix = f"{self.mission_id}:"
        if execution_id.startswith(prefix):
            body = execution_id[len(prefix):]
            return body.rsplit(":", 1)[0]
        return execution_id

    def execute(self, prompt: str, *, task_id: str | None = None, **kwargs: Any) -> Any:
        if not task_id:
            return self.runtime.execute(prompt, task_id=task_id, **kwargs)
        memory = self.memory_store.load(self.mission_id)
        if memory is not None:
            memory.begin_execution(self._graph_task_id(task_id), task_id)
            self.memory_store.save(memory)
        try:
            result = self.runtime.execute(prompt, task_id=task_id, **kwargs)
        except BaseException:
            # Keep the active execution durable: a later resume can distinguish an
            # interrupted attempt from work that was never started.
            raise
        nested = self._nested_execution(result)
        verification = verify_execution(nested)
        if memory is not None and verification.verified:
            committed = dict(nested)
            committed["task_id"] = task_id
            memory.commit_execution(
                task_id=self._graph_task_id(task_id),
                execution_id=task_id,
                result=committed,
            )
            self.memory_store.save(memory)
        return result
