from __future__ import annotations

import time

from agent_core.execution_fence import ExecutionFence
from agent_core.execution_agent import AgentExecutor
from agent_core.reliable_executor import ReliableAgentExecutor
from backend.storage.execution_ledger import ExecutionLedger
from backend.storage.side_effect_ledger import SideEffectLedger
from tool_system.process_runner import IsolatedProcessRunner, ProcessLimits
from agent_core.network_sandbox import NetworkSandbox


def _fence(tmp_path):
    db = tmp_path / "tasks.db"
    ledger = ExecutionLedger(db)
    effects = SideEffectLedger(db)
    attempt = ledger.begin("task-1", "worker-1", execution_id="exec-1")
    return ExecutionFence(task_id="task-1", execution_id="exec-1", fencing_token=attempt["fencing_token"], ledger=ledger, side_effects=effects)


def test_reliable_executor_binds_fence_to_all_mutation_tools(tmp_path):
    fence = _fence(tmp_path)
    executor = AgentExecutor.__new__(AgentExecutor)
    executor.workspace = tmp_path
    reliable = ReliableAgentExecutor.__new__(ReliableAgentExecutor)
    reliable.execution_fence = fence
    reliable.network_policy = __import__("agent_core.network_policy", fromlist=["NetworkPolicy"]).NetworkPolicy()
    reliable._bind_execution_fence(executor)
    assert executor.write_file.execution_fence is fence
    assert executor.make_directory.execution_fence is fence
    assert executor.copy_file.execution_fence is fence
    assert executor.move_file.execution_fence is fence
    assert executor.delete_file.execution_fence is fence
    assert executor.terminal.execution_fence is fence


def test_process_runner_aborts_when_fence_callback_reports_stale(tmp_path):
    runner = IsolatedProcessRunner(environment={"PATH": __import__("os").environ.get("PATH", "")}, network_sandbox=NetworkSandbox("command-policy"))
    started = time.monotonic()
    stdout, stderr, code, timed_out = runner.run(
        ["python", "-c", "import time; time.sleep(30)"],
        cwd=str(tmp_path),
        limits=ProcessLimits(timeout_seconds=30, max_output_chars=2000),
        should_terminate=lambda: True,
    )
    elapsed = time.monotonic() - started
    assert elapsed < 5
    assert code == 125
    assert not timed_out
    assert "execution fence was lost" in stderr.lower()
