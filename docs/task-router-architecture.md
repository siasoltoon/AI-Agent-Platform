# Task Router / Command Registry Architecture

## Purpose

The Task Router is the controller-side dispatch boundary between the canonical Task Contract and execution services. It selects an allowed task handler, validates the contract, preserves lifecycle semantics, and delegates execution without implementing worker internals.

## Boundaries

```text
API / Dashboard
      |
      v
Task Contract v1
      |
      v
Task Router
  |       |
  v       v
Registry  Queue
  |       |
  +---+---+
      v
Task Runner / Worker Client
      |
      v
PC Worker -> Agent Runtime -> Tools -> Evidence
```

## Registry

Each command has a stable name, handler, input contract, capability metadata, timeout policy, retry policy, and authorization boundary. Unknown commands fail closed. Registry entries are deterministic and testable.

## Queue

Queue-backed execution must preserve task IDs, lifecycle transitions, idempotency, bounded retries, cancellation semantics, and observable execution metadata. A queued task must never be reported completed before worker evidence is persisted.

## Reliability

- Validate before enqueue.
- Reject unknown or malformed commands.
- Prevent duplicate execution using task identity/idempotency rules.
- Apply bounded retry policy only to recoverable failures.
- Preserve real worker error details.
- Keep timeout limits bounded by execution profile.
- Make shutdown graceful and leave recoverable work in a valid lifecycle state.

## Extensibility

New bot projects should add domain task contracts and handlers through the registry rather than modifying the core execution path. This keeps the platform reusable for Forex, LifeVerse, Casino, cybersecurity education, and future agents.
