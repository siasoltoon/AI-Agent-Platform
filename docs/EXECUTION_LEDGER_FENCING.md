# Execution Attempt Ledger & Fencing

The worker lease prevents concurrent ownership, but a lease alone cannot stop an old worker from finishing after its lease expires. The execution ledger adds durable attempt identity and a monotonic fencing token.

## Attempt identity

Each claimed task receives:

- `execution_id`: globally unique execution identity
- `attempt_no`: monotonically increasing task attempt number
- `worker_id`: controller/worker owner
- `fencing_token`: monotonically increasing per-task ownership token
- `state`: `running`, `ambiguous`, `committed`, `superseded`, `failed`, or `cancelled`

The ledger is stored in the same SQLite database as tasks and leases.

## Fencing invariant

A worker may complete a task only when its execution is still the current ledger attempt and its fencing token is the current maximum token for that task. Completion updates the ledger and `tasks` row in one SQLite transaction.

Therefore an expired worker can finish its local computation, but it cannot durably publish completion after a newer attempt has fenced it out.

## Side-effect boundary

`ExecutionFence` extends the invariant to side-effect-capable tools. Before a mutation is started, the current execution/fencing token is checked. A durable `SideEffectLedger` records the logical mutation request using a deterministic idempotency key and request hash.

A previously committed side effect can be returned without executing the mutation again. A side effect belonging to another execution, or an effect whose outcome is `ambiguous`, is rejected rather than replayed. This makes file/process mutation a separate evidence boundary instead of treating the controller's completion record as proof that the underlying side effect happened exactly once.

The side-effect ledger lives in the same SQLite database and is intentionally conservative: ambiguous outcomes require explicit operator-directed recovery or a downstream idempotency/fencing guarantee.

## Idempotency

An optional `metadata.idempotency_key` identifies a logical request. Repeated creation with the same task/key returns the existing attempt rather than creating a second logical request. Committed results are retained in the ledger so a duplicate request can restore the durable result without executing side effects again.

## Recovery semantics

Startup recovery follows this order:

1. Preserve tasks with a live lease.
2. Reconcile professional mission state first.
3. Mark orphaned running attempts as `ambiguous`.
4. Mark the corresponding task failed with `automatic_retry_suppressed=true`.
5. Never replay an orphaned side-effecting execution automatically.

Explicit retry creates a new execution attempt and therefore a new fencing token.

## Safety boundary

The execution ledger protects the controller's durable completion boundary. The side-effect ledger additionally records local mutation intent/outcome, but it cannot make an arbitrary OS process or external service transactional. For those boundaries, the tool must assert the execution fence immediately before mutation and the downstream operation should provide its own idempotency/fencing mechanism when available.
