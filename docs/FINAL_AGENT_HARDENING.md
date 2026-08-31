# Final Agent Hardening Contract

This document defines the completion boundary for autonomous software tasks, including Telegram-bot development missions.

## Completion authority

The model is never the source of truth for completion. Completion is accepted only after deterministic runtime evidence proves the task's observable acceptance criteria.

The authoritative chain is:

`user task -> real tool execution -> independent observation -> deterministic acceptance gate -> TaskRunner completion`

## Exact-content tasks

For tasks containing an explicit `exactly` file-content requirement, the acceptance gate now requires all of the following:

1. The requested content is extracted from the user task, not from model output.
2. The write evidence proves the actual write content equals the requested content.
3. A direct `read_file` observation proves the target exists.
4. The direct read content equals the requested content byte-for-byte as represented by the task text.
5. Any missing, ambiguous, or contradictory exact-content evidence fails closed.

Therefore `read == write` is insufficient. The required invariant is:

`requested == write == independently_read`

## Restricted tasks

When a task explicitly forbids unrelated modifications, the runner validates mutation records against the paths named by the task and rejects unscoped terminal mutations.

## Agent behavior

The execution agent remains bounded by the 32-step operational contract. It must inspect the current workspace, use real tools, recover from verification failures when possible, and cannot turn an unverified state into `completed` merely by returning a `done` action.

## Evidence requirements

Evidence must explicitly identify the observable target and the checks that prove it. Model summaries are informational only. A successful HTTP request, a successful tool invocation, or `read == write` alone is not completion proof.

## Telegram-bot mission readiness

For larger Telegram-bot tasks, the same completion boundary applies to every concrete acceptance criterion: source files, configuration, migrations, tests, generated assets, integrations, worker behavior, and deployment artifacts must be proven by the appropriate deterministic checks before the task is considered complete.

The platform may still require environment-specific acceptance on the PC worker, Ollama runtime, Telegram network access, credentials, external APIs, and deployment infrastructure. Those are runtime acceptance concerns, not reasons to weaken the evidence gate.
