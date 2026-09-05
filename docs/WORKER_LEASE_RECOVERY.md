# Worker Lease and Recovery Semantics

The controller now treats task execution ownership as durable state rather than an in-process assumption.

## Execution identity

Every claimed task execution receives a new `execution_id` and runs under a durable `(task_id, worker_id, execution_id)` lease stored in the same SQLite database used by the task controller. Only the exact worker/execution identity may renew or release that lease.

An active unexpired lease blocks a second execution owner. An expired lease may be replaced by a new execution identity only after the prior ownership window has ended.

## Heartbeats

`SafeTaskRunner` renews the lease on a bounded heartbeat interval while worker execution is in progress. The heartbeat interval is constrained to at most half of the lease TTL.

If renewal fails or ownership disappears, the router result is rejected before the normal task completion path can persist `completed`. The task is marked failed with `execution_ambiguous`, `automatic_retry_suppressed`, and `recovery_required` metadata.

## Startup recovery

Controller startup no longer calls the old blind `recover_running_tasks()` replay path from `SafeTaskRunner`.

`RecoverySweep` applies conservative rules:

- Running task with a live lease: preserve it.
- Running task with no live owner: fail it as an orphaned ambiguous execution; never auto-requeue it.
- Expired lease: purge it and preserve its `execution_id` in task recovery metadata for forensic inspection.
- Professional mission: run deterministic Task/Mission reconciliation first. A durably verified and accepted mission may repair stale Task state to completed.
- Unverified or still-running mission without a live execution owner: never infer success and never auto-replay.

## Safety invariant

A controller restart, worker crash, transport ambiguity, or stale heartbeat must not cause the same side-effecting task to execute twice automatically.

Explicit operator recovery remains possible through the existing retry/reconciliation mechanisms, but automatic recovery is limited to state transitions supported by durable evidence.
