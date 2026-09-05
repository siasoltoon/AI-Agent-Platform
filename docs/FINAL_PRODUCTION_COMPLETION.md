# AI Agent Platform — Final Production Completion

## Scope

This document defines the production baseline for the local PC Worker + Ollama execution architecture.

### Controller
- Durable SQLite task persistence.
- Canonical task contract and lifecycle validation.
- Queue/claim execution model.
- Cancellation as an authoritative terminal state.
- Controller restart recovery for interrupted `running` tasks.
- Bounded automatic retries with retry audit events.
- Real execution evidence required before completion.
- Durable execution-attempt ledger with monotonic fencing tokens.
- Atomic fenced task completion so stale workers cannot publish completion.
- Conservative orphan-attempt recovery with `ambiguous` state when outcome is not provable.

### Agent
- Bounded plan/act/observe/verify loop.
- Structured JSON action contract.
- Dedicated workspace/file tools.
- Controlled terminal tool with development toolchain aliases.
- Workspace path containment enforcement.
- Mutation verification and exact content verification.
- Recovery from tool failures when possible.
- Rejection of false-positive completion claims.
- Large-task orchestration through the existing multi-step path.
- Execution fence propagated to side-effect-capable tools.
- Durable side-effect ledger with deterministic idempotency keys.
- Committed side effects are replayed from durable results rather than executed twice.
- Ambiguous side effects are never blindly replayed.

### Worker
- Real Ollama-backed execution on the PC.
- Request validation and hard bounds.
- Single-execution lock for the current worker process.
- Worker health diagnostics.
- Explicit failure propagation to the controller.
- Configurable agent step and execution timeout bounds.
- Execution identity and fencing metadata propagated through the execution path.
- Fence-aware process execution terminates stale work rather than allowing detached mutation to continue.

### Storage
- SQLite connections are explicitly closed on every operation.
- Indexed task/event lookups.
- Append-only execution audit events.
- Atomic queued-task claiming.
- Atomic retry requeue.
- Lifecycle transitions cannot be bypassed through the generic update path.
- Authoritative execution-attempt summaries are exposed for diagnostics and dashboard telemetry.
- Authoritative side-effect summaries are exposed for diagnostics and dashboard telemetry.

### API and Dashboard
- Task creation returns `202` and durable task identity.
- Task state can be queried independently of execution.
- Task events are available for audit/history.
- Cancellation endpoint is available.
- Liveness and readiness probes are available.
- Existing dashboard compatibility endpoints remain intact.
- Dashboard summary exposes execution-attempt and side-effect state from the durable ledgers.
- Dashboard diagnostics explicitly fails when the execution fence ledger is unavailable.

## Crash/race safety verification

The regression suite now covers the critical execution-fence failure modes:
- A stale execution cannot commit after a newer execution obtains a higher fencing token.
- Recovery marks an orphaned execution as `ambiguous` rather than pretending its outcome is known.
- An ambiguous side effect cannot be automatically replayed.
- A committed side effect is returned from its durable ledger record instead of being executed again.

These tests complement the end-to-end execution fencing and worker lease recovery tests.

## Operational contract

A task may be reported as `completed` only when the Worker returns a structured execution result and its `execution_evidence.verified` flag is true. A textual claim by the model is never sufficient.

A task that fails execution is either retried within its bounded retry budget or becomes `failed` with the real error recorded. A cancelled task cannot be converted back into a successful task by a late Worker response.

A Worker execution is authoritative only while its execution fence remains current. A stale execution may finish in memory, but it cannot durably publish task completion or begin a new side effect. Side-effect outcomes that cannot be proven are preserved as `ambiguous` and require explicit recovery rather than blind replay.

All filesystem operations performed by the Agent must remain inside the configured workspace. Dedicated file tools are preferred over shell mutation commands.

## PC deployment baseline

Run the Worker from the repository workspace:

```powershell
cd D:\AI_Workspace\AI-Agent-Platform
python -m uvicorn worker_system.worker:app --host 0.0.0.0 --port 8001 --log-level info
```

The controller should point to the PC Worker using the existing worker configuration. Ollama remains the local model runtime.

## Release gate

The repository release gate is:

```powershell
python -m pytest -q
python scripts/production_gate.py
```

The expected final gate state is:

```text
PRODUCTION GATE: PASSED
```

The test suite is a regression safety net; the production gate is the release decision. Future feature work should extend this baseline rather than replacing the execution contract.
