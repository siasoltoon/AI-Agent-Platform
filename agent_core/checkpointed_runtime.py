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
    def _execution_result(result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {}
        if "status" in result or "execution_evidence" in result or "tool_records" in result:
            return result
        nested = result.get("result")
        if isinstance(nested, dict):
            if "status" in nested or "execution_evidence" in nested or "tool_records" in nested:
                return nested
            nested = nested.get("result")
            if isinstance(nested, dict):
                return nested
        return {}

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
        graph_task_id = self._graph_task_id(task_id)
        if memory is not None:
            memory.begin_execution(graph_task_id, task_id)
            self.memory_store.save(memory)
        try:
            result = self.runtime.execute(prompt, task_id=task_id, **kwargs)
        except BaseException:
            raise
        execution = dict(self._execution_result(result))
        verification = verify_execution(execution)
        if memory is not None and verification.verified:
            execution["task_id"] = task_id
            memory.commit_execution(task_id=graph_task_id, execution_id=task_id, result=execution)
            self.memory_store.save(memory)
        return result
