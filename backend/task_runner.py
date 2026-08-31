"""Durable background executor for controller tasks."""

from __future__ import annotations

import os
import re
import threading
import time

from task_engine.contracts import TaskRequest, TaskStatus


class TaskRunner:
    """Run persisted tasks outside HTTP with bounded retries and cancellation safety."""

    def __init__(self, store, router, *, poll_seconds: float = 0.25, default_retries: int = 2) -> None:
        self.store = store
        self.router = router
        self.poll_seconds = max(0.05, float(poll_seconds))
        self.default_retries = max(0, min(int(default_retries), 5))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lifecycle_lock = threading.Lock()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        with self._lifecycle_lock:
            if self.running:
                return
            self.store.recover_running_tasks()
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="task-runner", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lifecycle_lock:
            self._stop.set()
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            task = self.store.claim_next_queued()
            if task is None:
                self._stop.wait(self.poll_seconds)
                continue
            self._execute(task)

    @staticmethod
    def _retry_budget(metadata: dict) -> int:
        try:
            value = int(metadata.get("max_retries", 2))
        except (TypeError, ValueError):
            value = 2
        return max(0, min(value, 5))

    @staticmethod
    def _retry_count(metadata: dict) -> int:
        try:
            return max(0, int(metadata.get("retry_count", 0)))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _execution_evidence(result: dict) -> dict | None:
        """Extract the canonical agent evidence through the runtime/worker envelope."""
        candidates = [result]
        nested = result.get("result")
        if isinstance(nested, dict):
            candidates.append(nested)
            nested_result = nested.get("result")
            if isinstance(nested_result, dict):
                candidates.append(nested_result)
        for candidate in candidates:
            evidence = candidate.get("execution_evidence")
            if isinstance(evidence, dict):
                return evidence
        return None

    @staticmethod
    def _tool_records(result: dict) -> list[dict]:
        """Extract canonical tool records from the runtime/worker envelope."""
        candidates = [result]
        nested = result.get("result")
        if isinstance(nested, dict):
            candidates.append(nested)
            nested_result = nested.get("result")
            if isinstance(nested_result, dict):
                candidates.append(nested_result)
        for candidate in candidates:
            records = candidate.get("tool_records")
            if isinstance(records, list):
                return [record for record in records if isinstance(record, dict)]
        return []

    @staticmethod
    def _evidence_satisfies_task(prompt: str, evidence: dict) -> bool:
        """Require evidence to prove the observable object named by a file task."""
        checks = evidence.get("checks")
        if not isinstance(checks, list):
            return False

        file_mentions = re.findall(
            r"(?<![\w/])(?:[\w.-]+/)*[\w.-]+\.[A-Za-z0-9]{1,12}(?![\w])",
            str(prompt),
        )
        if not file_mentions:
            return True

        normalized_mentions = {path.lower() for path in file_mentions}
        observable_types = {"file_exists", "read_verified_exists", "file_content_matches_write", "file_content_readable"}
        matching = []
        for check in checks:
            if not isinstance(check, dict) or check.get("type") not in observable_types:
                continue
            path = str(check.get("path", "")).replace("\\", "/").lower()
            if any(path == mention or path.endswith("/" + mention) for mention in normalized_mentions):
                matching.append(check)

        if not matching or not all(check.get("passed") is True for check in matching):
            return False

        lower = str(prompt).lower()
        if "exactly" in lower and not any(
            check.get("type") == "file_content_matches_write" and check.get("passed") is True
            for check in matching
        ):
            return False
        return True

    @staticmethod
    def _scope_restricted(prompt: str) -> bool:
        """Detect tasks that explicitly forbid unrelated workspace side effects."""
        lower = str(prompt).lower()
        patterns = (
            "do not modify or delete any other",
            "do not modify any other",
            "do not delete any other",
            "do not change any other",
            "do not modify/delete any other",
            "nothing else",
            "no other files",
            "no other file",
            "without modifying anything else",
            "without changing anything else",
        )
        return any(pattern in lower for pattern in patterns)

    @staticmethod
    def _requested_paths(prompt: str) -> set[str]:
        mentions = re.findall(
            r"(?<![\w/])(?:[\w.-]+/)*[\w.-]+\.[A-Za-z0-9]{1,12}(?![\w])",
            str(prompt),
        )
        return {path.replace("\\", "/").lower().lstrip("./") for path in mentions}

    @classmethod
    def _scope_satisfies_task(cls, prompt: str, result: dict) -> tuple[bool, dict]:
        """Validate mutation records against an explicitly restricted task scope.

        This is intentionally a conservative completion gate: for tasks that say
        not to modify anything else, every recorded mutation must target a path
        explicitly named by the task. A terminal mutation is also rejected when
        its command cannot be safely scoped to a named path.
        """
        requested = cls._requested_paths(prompt)
        if not cls._scope_restricted(prompt):
            return True, {"scope_verified": False, "scope_restricted": False, "unexpected_paths": []}

        records = cls._tool_records(result)
        mutations: list[str] = []
        unscoped_terminal: list[str] = []

        def add_path(value: object) -> None:
            if value is None:
                return
            path = str(value).replace("\\", "/").strip().lower().lstrip("./")
            if path:
                mutations.append(path)

        for record in records:
            if record.get("ok") is not True:
                continue
            tool = str(record.get("tool", "")).lower()
            payload = record.get("result")
            payload = payload if isinstance(payload, dict) else {}
            if tool == "write_file":
                add_path(payload.get("path"))
            elif tool == "make_directory":
                add_path(payload.get("path"))
            elif tool in {"copy_file", "move_file"}:
                add_path(payload.get("source"))
                add_path(payload.get("destination"))
            elif tool == "delete_file":
                add_path(payload.get("path"))
            elif tool in {"terminal", "mkdir", "mktemp", "echo"}:
                command = str(payload.get("command", "")).strip()
                first = command.split(maxsplit=1)[0].lower() if command else tool
                if first in {"mkdir", "md"}:
                    add_path(command.split(maxsplit=1)[1] if len(command.split(maxsplit=1)) > 1 else "")
                elif re.search(r"(?:>|>>|del(?:ete)?\s+|erase\s+|move\s+|copy\s+)", command, re.IGNORECASE):
                    unscoped_terminal.append(command)

        unexpected = sorted({path for path in mutations if path not in requested})
        scope_verified = not unexpected and not unscoped_terminal and bool(requested)
        return scope_verified, {
            "scope_verified": scope_verified,
            "scope_restricted": True,
            "requested_paths": sorted(requested),
            "mutation_paths": sorted(set(mutations)),
            "unexpected_paths": unexpected,
            "unscoped_terminal_commands": unscoped_terminal,
        }

    def _fail_or_retry(self, task_id: str, record: dict, error: str) -> None:
        if self.store.is_cancelled(task_id):
            return
        metadata = dict(record.get("metadata", {}))
        retries = self._retry_count(metadata)
        budget = self._retry_budget(metadata)
        if retries < budget:
            metadata.update({"retry_count": retries + 1, "last_error": error, "retry_at": time.time()})
            self.store.requeue_for_retry(task_id, metadata=metadata, error=error)
            return
        self.store.update(
            task_id,
            status=TaskStatus.FAILED.value,
            completed_at=time.time(),
            error=error,
            metadata={**metadata, "retry_count": retries, "max_retries": budget},
        )

    def _execute(self, record: dict) -> None:
        task_id = record["id"]
        if self.store.is_cancelled(task_id):
            return

        metadata = dict(record.get("metadata", {}))
        task = TaskRequest(
            prompt=record["prompt"],
            model=record.get("model"),
            task_id=task_id,
            timeout_seconds=metadata.get("timeout_seconds"),
            metadata=metadata,
        )
        started = time.time()
        try:
            result = self.router.route(task, task_id=task_id)
            if self.store.is_cancelled(task_id):
                return

            evidence = self._execution_evidence(result) if isinstance(result, dict) else None
            if not isinstance(evidence, dict) or evidence.get("verified") is not True:
                raise RuntimeError("Task execution completed without verified execution evidence.")
            if not self._evidence_satisfies_task(record["prompt"], evidence):
                raise RuntimeError("Task execution completed with evidence that does not prove the requested file state.")

            scope_ok, scope_evidence = self._scope_satisfies_task(record["prompt"], result if isinstance(result, dict) else {})
            if not scope_ok:
                evidence = {**evidence, **scope_evidence}
                raise RuntimeError("Task execution completed with unauthorized workspace side effects.")
            evidence = {**evidence, **scope_evidence}

            current = self.store.get(task_id) or record
            execution_metadata = {
                "execution_mode": result.get("execution_mode", "agentic"),
                "duration_seconds": round(time.time() - started, 3),
                "retry_count": self._retry_count(current.get("metadata", {})),
                "execution_evidence": evidence,
            }
            nested = result.get("result")
            if isinstance(nested, dict):
                execution_metadata.update({
                    "steps": nested.get("steps", 1),
                    "orchestration_mode": nested.get("mode", "agentic"),
                })
                nested_result = nested.get("result")
                if isinstance(nested_result, dict):
                    execution_metadata["steps"] = nested_result.get("steps", execution_metadata["steps"])
                    execution_metadata["orchestration_mode"] = nested_result.get("mode", execution_metadata["orchestration_mode"])
            self.store.update(
                task_id,
                status=TaskStatus.COMPLETED.value,
                completed_at=time.time(),
                result=result,
                error=None,
                metadata={**current.get("metadata", {}), **execution_metadata},
            )
        except TimeoutError as exc:
            self._fail_or_retry(task_id, record, str(exc) or "Task execution timed out.")
        except Exception as exc:
            self._fail_or_retry(task_id, record, str(exc) or "Task execution failed.")


DEFAULT_POLL_SECONDS = float(os.getenv("TASK_RUNNER_POLL_SECONDS", "0.25"))
DEFAULT_TASK_RETRIES = max(0, min(int(os.getenv("TASK_RUNNER_MAX_RETRIES", "2")), 5))
