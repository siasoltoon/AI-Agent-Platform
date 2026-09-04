# Professional Agent Execution Architecture

This document defines the engineering direction for heavy autonomous software missions.

## Mission lifecycle

1. **Contract** — derive explicit acceptance requirements from the objective.
2. **Reconnaissance** — inspect repository structure, dependencies, conventions, and existing tests before mutation.
3. **Planning** — decompose work into bounded dependency-aware tasks.
4. **Execution** — perform real tool actions inside the configured workspace.
5. **Observation** — collect filesystem, command, and execution evidence from the real environment.
6. **Verification** — independently validate completion instead of trusting model claims.
7. **Recovery** — classify failures and repair root causes before retrying.
8. **Acceptance** — complete only when the mission contract and evidence gates pass.
9. **Persistence** — checkpoint state so interrupted missions can resume without blindly repeating completed work.

## Engineering principles

- Model output is a proposal, never proof of completion.
- Tool execution and observable state are authoritative.
- Read-only constraints are machine-enforced and remain active during recovery.
- Recovery is bounded and must not recursively expand forever.
- Heavy missions use orchestration rather than relying on one enormous model context.
- Testing is requirement-aware: code changes require test evidence; documentation-only work does not get blocked by an unrelated test requirement.
- Evidence counters are cross-checked against actual tool records before acceptance.
- Security, reliability, performance, and maintainability are treated as execution concerns, not post-processing.
- The platform should prefer deterministic gates for safety-critical decisions and use the model for planning, implementation, diagnosis, and adaptation.

## Current architecture

`Task API -> durable TaskRunner -> AgentRuntime -> PC Worker -> ReliableAgentExecutor -> AgentExecutor -> bounded tools -> evidence -> verification -> acceptance`

Long-running developer missions additionally use:

`AutonomousDeveloper -> TaskGraph + MissionMemory + AdaptivePlanner + MissionContextManager + MissionAcceptanceGate`

The architecture is intentionally incremental. Each hardening stage must preserve the existing production path and add executable evidence rather than creating parallel fake implementations.
