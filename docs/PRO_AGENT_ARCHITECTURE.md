# Professional Agent Execution Architecture

This document defines the engineering direction for heavy autonomous software missions.

## Mission lifecycle

1. **Contract** — derive explicit acceptance requirements and capabilities from the objective.
2. **Reconnaissance** — inspect repository structure, dependencies, conventions, and existing tests before mutation.
3. **Planning** — decompose work into bounded dependency-aware tasks.
4. **Capability authorization** — authorize requested execution capabilities against the mission contract; restrictions may be strengthened, never weakened.
5. **Execution** — perform real tool actions inside the configured workspace and authorized network boundary.
6. **Observation** — collect filesystem, command, network-containment, and execution evidence from the real environment.
7. **Verification** — independently validate completion, resource boundaries, and capability compliance instead of trusting model claims.
8. **Recovery** — classify failures and repair root causes before retrying.
9. **Acceptance** — complete only when the mission contract and evidence gates pass.
10. **Persistence** — checkpoint state so interrupted missions can resume without blindly repeating completed work.
11. **Finalization** — after a terminal completed/cancelled state is durably reached, clear the active execution identity while preserving the final checkpoint evidence.

## Engineering principles

- Model output is a proposal, never proof of completion.
- Tool execution and observable state are authoritative.
- Read-only constraints are machine-enforced and remain active during recovery.
- Execution capabilities are contract-bound: a worker cannot escalate network access above the mission contract.
- Native network isolation is fail-closed when the host cannot establish the requested containment.
- Recovery is bounded and must not recursively expand forever.
- Heavy missions use orchestration rather than relying on one enormous model context.
- Mission execution controls are invocation-scoped; orchestration must not mutate a shared developer runtime while another mission may be executing.
- Model, timeout, and mission metadata are propagated through the orchestration boundary into the runtime/worker contract rather than being stored only as response decoration.
- Testing is requirement-aware: code changes require test evidence; documentation-only work does not get blocked by an unrelated test requirement.
- Evidence counters are cross-checked against actual tool records before acceptance.
- Security, reliability, performance, and maintainability are treated as execution concerns, not post-processing.
- Terminal missions clear stale active-execution identity only after the terminal state is reached, while retaining a checkpoint that records the finalization event.
- Lifecycle events are durably ordered in mission memory, allowing audit, diagnostics, and resume tooling to reconstruct the orchestrator's phase history.
- Event persistence occurs before an external event sink is notified, so observability consumers cannot become the source of truth or prevent durable history from being recorded.
- Operational inspection is read-only and bounded: callers can retrieve a mission snapshot and a limited suffix of its event history without mutating mission state.
- Cancellation from the Task API must traverse the professional MissionService for `mission.execute` tasks so mission memory reaches a durable terminal state and records the cancellation event; worker cancellation remains the final execution-layer signal.
- Production controller instances persist mission snapshots in the same SQLite database used by the task control plane, so mission state survives controller restart instead of relying only on process-local memory.
- Durable mission loads prefer the external persistence adapter over the local cache, preventing a stale process-local snapshot from overriding newer state written by another controller instance.
- Active execution outcomes are explicit: `running`, `interrupted`, `ambiguous`, and `committed`. A task is advanced only from a committed, independently verified outcome.
- Worker/process exceptions persist an `interrupted` outcome before the exception is propagated to the bounded recovery loop; unverified returns persist an `ambiguous` outcome so a later resume never treats an unverified response as proof of completion.
- Resume reconciliation is conservative: only a matching, independently verified committed execution can advance the graph. Interrupted or ambiguous executions remain uncommitted and receive an explicit recovery checkpoint before retry.
- The durable memory adapter protects a stronger execution outcome from being overwritten by a stale in-process snapshot when concurrent/restarted control paths save mission state.
- The platform should prefer deterministic gates for safety-critical decisions and use the model for planning, implementation, diagnosis, and adaptation.

## Current architecture

`Task API -> durable TaskRunner -> MissionOrchestrator -> AutonomousDeveloper -> MissionContract -> Capability Authorization -> AgentRuntime -> PC Worker -> Worker Isolation -> ReliableAgentExecutor -> AgentExecutor -> bounded tools -> NetworkPolicy -> NetworkSandbox -> isolated process -> evidence -> verification -> acceptance`

Long-running developer missions additionally use:

`AutonomousDeveloper -> TaskGraph + MissionMemory + AdaptivePlanner + MissionContextManager + MissionAcceptanceGate`

Network capability modes are ordered from most restrictive to least restrictive:

`deny < restricted < native < allow`

A mission may request a mode at or below its contract mode. `native` additionally requires observable native containment evidence; if native containment cannot be established, execution is rejected instead of silently falling back to a weaker mode.

Mission execution parameters (`model`, `timeout_seconds`, and metadata) are passed as invocation-local controls. Checkpointing wraps only that invocation's runtime, so concurrent missions cannot overwrite each other's runtime adapter.

Acceptance exposes network capability compliance as an explicit gate in addition to verification, making capability failures visible as a deterministic acceptance reason rather than an implicit side effect of a generic verification failure.

Terminal checkpoint finalization is performed by the orchestrator after the developer reaches `completed` or `cancelled`. The final checkpoint preserves the active execution ID for auditability, then the active execution fields are cleared so a terminal mission cannot be mistaken for an interrupted in-flight execution on a later resume.

The orchestrator also persists an ordered lifecycle event stream (`contract -> recon -> plan -> execute -> verify -> accept -> terminal`) inside the same mission memory record. This is intentionally a compact audit history rather than a replacement for execution evidence: tool records and verification remain authoritative for what actually happened.

The mission service exposes a read-only inspection surface at `GET /tasks/{task_id}/mission`. It returns the durable mission snapshot plus `event_count` and a bounded event suffix (`event_limit`, 1–1000). A truncated response is explicitly marked with `events_truncated` so operators never mistake a bounded view for the complete history.

Production task dispatch now wires MissionService to `SQLiteMissionStore` using the controller's `TASK_DB_PATH`. The store atomically upserts complete mission snapshots, supports bounded status-filtered listing, and shares the controller database without changing the TaskStore schema.

Execution recovery now records the outcome around the external runtime boundary. Before side effects, the exact execution ID is persisted as `running`. Exceptions become `interrupted`; returns without independently verified evidence become `ambiguous`; verified results become `committed`. This makes crash/retry behavior observable and prevents recovery code from silently promoting an uncertain execution into completed graph state.

The architecture is intentionally incremental. Each hardening stage must preserve the existing production path and add executable evidence rather than creating parallel fake implementations.
