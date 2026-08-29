"""Final production-readiness gate for the AI Agent Platform.

This gate intentionally uses only local Python/runtime checks. It does not perform
analytics, telemetry collection, or network discovery. Run it from the repository
root before promoting a build.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REQUIRED_MODULES = (
    "agent_core.execution_agent",
    "agent_core.runtime",
    "backend.main",
    "backend.task_runner",
    "backend.storage.task_store",
    "task_engine.contracts",
    "task_engine.lifecycle",
    "task_engine.registry",
    "task_engine.router",
    "tool_system.file_tools",
    "tool_system.terminal_tools",
    "worker_system.worker",
)


def check_imports() -> list[str]:
    failures: list[str] = []
    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:  # pragma: no cover - diagnostic gate
            failures.append(f"import {name}: {type(exc).__name__}: {exc}")
    return failures


def check_lifecycle() -> list[str]:
    from task_engine.lifecycle import can_transition

    expected = (
        ("queued", "running", True),
        ("queued", "cancelled", True),
        ("running", "queued", True),
        ("running", "completed", True),
        ("running", "failed", True),
        ("running", "cancelled", True),
        ("completed", "running", False),
        ("failed", "running", False),
        ("cancelled", "running", False),
    )
    return [
        f"lifecycle {current}->{target}: expected {wanted}, got {can_transition(current, target)}"
        for current, target, wanted in expected
        if can_transition(current, target) is not wanted
    ]


def check_task_store() -> list[str]:
    from task_engine.contracts import TaskStatus
    from backend.storage.task_store import TaskStore

    with tempfile.TemporaryDirectory(prefix="agent-platform-gate-") as directory:
        store = TaskStore(Path(directory) / "tasks.db")
        task = {
            "id": "gate-task",
            "prompt": "production gate",
            "model": "qwen2.5-coder:7b",
            "status": TaskStatus.QUEUED.value,
            "created_at": 1.0,
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
            "metadata": {},
        }
        store.create(task)
        claimed = store.claim_next_queued()
        if not claimed or claimed["status"] != TaskStatus.RUNNING.value:
            return ["TaskStore could not claim a queued task."]
        if store.list()[0]["id"] != "gate-task":
            return ["TaskStore newest-first ordering failed."]
        if not store.events("gate-task"):
            return ["TaskStore audit events were not recorded."]
        return []


def check_tools() -> list[str]:
    from agent_core.execution_agent import AgentExecutor
    from tool_system.terminal_tools import TerminalTool

    failures: list[str] = []
    required = {"read_file", "write_file", "file_exists", "directory_exists", "list_directory", "make_directory", "search_files", "copy_file", "move_file", "delete_file", "file_hash", "terminal"}
    missing = required - AgentExecutor._TOOLS
    if missing:
        failures.append(f"AgentExecutor missing tools: {sorted(missing)}")
    if "git" not in TerminalTool._ALLOWED:
        failures.append("Terminal toolchain does not allow git.")
    if "python" not in TerminalTool._ALLOWED:
        failures.append("Terminal toolchain does not allow python.")
    if "node" not in TerminalTool._ALLOWED:
        failures.append("Terminal toolchain does not allow node.")
    return failures


def main() -> int:
    os.environ.setdefault("ENVIRONMENT", "test")
    failures: list[str] = []
    failures.extend(check_imports())
    if not failures:
        failures.extend(check_lifecycle())
        failures.extend(check_task_store())
        failures.extend(check_tools())

    if failures:
        print("PRODUCTION GATE: FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("PRODUCTION GATE: PASSED")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Repository: {ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
