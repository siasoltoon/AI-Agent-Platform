# Final Production Readiness

This branch defines the production execution boundary for AI-Agent-Platform.

## Completion contract

A task may become `completed` only when all of the following are true:

1. The task has a durable execution attempt with an execution ID and fencing token.
2. The real agent execution produced observable evidence.
3. Independent execution verification passed.
4. The execution fence is still current.
5. Completion is committed through the fenced execution ledger transaction.

A restart may reconcile a durable committed attempt without replaying the agent. An execution that has been superseded cannot restore completion.

## Recovery contract

Recovery is conservative and durable:

- stale worker leases are reconciled through `RecoverySweep`;
- orphaned executions are fenced before terminalization;
- ambiguous execution outcomes are not blindly replayed;
- committed attempts may be restored idempotently after a crash;
- a newer fencing token always wins over an older execution.

## Side-effect contract

Mutation-capable tools use `ExecutionFence` and `SideEffectLedger`.

- idempotency keys are task-scoped and deterministic;
- request hashes must match the recorded request identity;
- stale executions cannot commit side effects;
- committed side effects can be returned as idempotent replays;
- ambiguous or failed side effects are not automatically replayed;
- ownership is revalidated before commit.

External side effects remain inherently non-transactional with the local SQLite ledger. If a worker can disappear after an external mutation and before the ledger commit, the outcome is recorded as ambiguous rather than pretending that the operation is safe to repeat.

## Production boundary

The controller starts `SafeTaskRunner`, `RecoverySweep`, `ExecutionLedger`, and `WorkerLeaseStore`. The legacy task runner is not the production execution path.

The repository CI gate validates deterministic code, contract, recovery, security, frontend, and dashboard behavior. Live PC-worker/Ollama acceptance remains environment-dependent and must be exercised on the synchronized worker host.

## Final acceptance checklist

- [x] Durable task lifecycle
- [x] Worker lease and stale-worker recovery
- [x] Execution attempt ledger
- [x] Monotonic fencing
- [x] Atomic fenced completion
- [x] Crash/restart reconciliation
- [x] Independent completion verification
- [x] Side-effect idempotency and ownership fencing
- [x] Ambiguous outcome protection
- [x] Production runtime boundary documentation
- [x] Final cross-component audit contract
- [x] Regression coverage for the above invariants

No claim is made here that a local PC/Ollama environment has been live-tested by repository CI; that remains a deployment acceptance responsibility.
