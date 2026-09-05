# Production Runtime Boundary

## Authoritative runtime

The production FastAPI lifespan uses `SafeTaskRunner`, `RecoverySweep`, `ExecutionLedger`, and `WorkerLeaseStore`. The legacy `TaskRunner` remains a compatibility/base implementation for focused tests and subclassing; it is not the production controller runner.

## Completion invariant

Production completion must follow:

```text
Task claim
  -> execution_id + fencing_token
  -> agent execution
  -> execution evidence
  -> independent verification
  -> execution fence check
  -> atomic ExecutionLedger.commit_task_if_current()
  -> tasks.status = completed
```

No late worker may publish `completed` after a newer execution owns the task.

## Restart/recovery invariant

Production startup must use `RecoverySweep` rather than the legacy `TaskStore.recover_running_tasks()` blind requeue path. Recovery preserves live ownership and fences orphaned executions before changing durable task state.

If an execution is already durably `committed` but the process crashes before the task row is published as `completed`, `RecoverySweep` restores completion from the durable execution result through `restore_committed_task_if_current()`. The restore is itself fenced and refuses to reconcile an older execution after a newer fencing token exists.

This distinction is intentional: a running task may already have performed an irreversible side effect, so converting every `running` row directly to `queued` would permit unsafe replay.

## Verification invariant

`ReliableAgentExecutor` applies `verify_execution()` as an independent completion gate. Evidence supplied by the model is therefore not sufficient by itself: completion requires successful tool observations, consistent evidence counters, policy/security compliance, and network capability compliance.

## Side-effect invariant

Mutation-capable tools use `ExecutionFence` and `SideEffectLedger`. A committed side effect is replayed from durable evidence; an ambiguous side effect is not automatically replayed.

## Audit rule

Any new production path that writes `tasks.status = completed` must either use `ExecutionLedger.commit_task_if_current()` or provide an equivalent atomic fencing transaction. Direct unfenced completion is considered a production correctness violation.
