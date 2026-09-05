"""Final production-readiness gate for the AI Agent Platform.

This gate intentionally uses only local Python/runtime checks. It does not perform
analytics, telemetry collection, or network discovery. Run it from the repository
root before promoting a build.
"""
from __future__ import annotations
import importlib, os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
REQUIRED_MODULES = ("agent_core.execution_agent", "agent_core.runtime", "agent_core.execution_fence", "backend.main", "backend.task_runner", "backend.storage.task_store", "backend.storage.execution_ledger", "backend.storage.side_effect_ledger", "task_engine.contracts", "task_engine.lifecycle", "task_engine.registry", "task_engine.router", "tool_system.file_tools", "tool_system.terminal_tools", "worker_system.worker")

def check_imports() -> list[str]:
    failures=[]
    for name in REQUIRED_MODULES:
        try: importlib.import_module(name)
        except Exception as exc: failures.append(f"import {name}: {type(exc).__name__}: {exc}")
    return failures

def check_lifecycle() -> list[str]:
    from task_engine.lifecycle import can_transition
    expected=(("queued","running",True),("queued","cancelled",True),("running","queued",True),("running","completed",True),("running","failed",True),("running","cancelled",True),("completed","running",False),("failed","running",False),("cancelled","running",False))
    return [f"lifecycle {c}->{t}: expected {w}, got {can_transition(c,t)}" for c,t,w in expected if can_transition(c,t) is not w]

def check_task_store() -> list[str]:
    from task_engine.contracts import TaskStatus
    from backend.storage.task_store import TaskStore
    with tempfile.TemporaryDirectory(prefix="agent-platform-gate-") as directory:
        store=TaskStore(Path(directory)/"tasks.db")
        store.create({"id":"gate-task","prompt":"production gate","model":"qwen2.5-coder:7b","status":TaskStatus.QUEUED.value,"created_at":1.0,"started_at":None,"completed_at":None,"result":None,"error":None,"metadata":{}})
        claimed=store.claim_next_queued()
        if not claimed or claimed["status"] != TaskStatus.RUNNING.value: return ["TaskStore could not claim a queued task."]
        if store.list()[0]["id"] != "gate-task": return ["TaskStore newest-first ordering failed."]
        if not store.events("gate-task"): return ["TaskStore audit events were not recorded."]
    return []

def check_tools() -> list[str]:
    from agent_core.execution_agent import AgentExecutor
    from tool_system.terminal_tools import TerminalTool
    failures=[]; required={"read_file","write_file","file_exists","directory_exists","list_directory","make_directory","search_files","copy_file","move_file","delete_file","file_hash","terminal"}
    missing=required-AgentExecutor._TOOLS
    if missing: failures.append(f"AgentExecutor missing tools: {sorted(missing)}")
    for executable in ("git","python","node"):
        if executable not in TerminalTool._ALLOWED: failures.append(f"Terminal toolchain does not allow {executable}.")
    return failures

def check_fencing() -> list[str]:
    from agent_core.execution_fence import ExecutionFence, ExecutionFenceError
    from backend.storage.execution_ledger import ExecutionLedger
    from backend.storage.side_effect_ledger import SideEffectLedger
    with tempfile.TemporaryDirectory(prefix="agent-platform-fence-") as directory:
        db=Path(directory)/"tasks.db"; ledger=ExecutionLedger(db); effects=SideEffectLedger(db)
        first=ledger.begin("gate-task","worker-1",execution_id="exec-1"); ledger.begin("gate-task","worker-2",execution_id="exec-2")
        fence=ExecutionFence(task_id="gate-task",execution_id="exec-1",fencing_token=int(first["fencing_token"]),ledger=ledger,side_effects=effects)
        try: fence.assert_current()
        except ExecutionFenceError: return []
        return ["Stale execution fence was not rejected."]

def main() -> int:
    os.environ.setdefault("ENVIRONMENT","test"); failures=check_imports()
    if not failures: failures.extend(check_lifecycle()); failures.extend(check_task_store()); failures.extend(check_tools()); failures.extend(check_fencing())
    if failures:
        print("PRODUCTION GATE: FAILED")
        for failure in failures: print(f"- {failure}")
        return 1
    print("PRODUCTION GATE: PASSED"); print(f"Python: {sys.version.split()[0]}"); print(f"Repository: {ROOT}"); return 0
if __name__ == "__main__": raise SystemExit(main())
