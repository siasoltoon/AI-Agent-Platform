# AI Agent Platform — Final Sync & Release Checklist

## Purpose

This document is the handoff point between repository-level completion and the final local-PC validation. Repository work may be completed without access to the PC; the final local gate must still be executed after synchronization because it is the only place that can validate the real PC Worker + Ollama environment.

## Repository baseline

The `main` branch contains the production dashboard control-center work and the hardened task execution path. The dashboard is dependency-light and served directly by FastAPI, while the React/Vite source remains available as the extensible frontend architecture.

The current repository contract includes:

- canonical Task Contract and validation
- durable SQLite task persistence
- queue/claim execution
- lifecycle enforcement and restart recovery
- authoritative cancellation
- bounded automatic retries
- explicit failed-task retry operation
- real Worker error propagation
- real agentic execution with observable evidence
- PC Worker + Ollama execution boundary
- production liveness/readiness probes
- production configuration and explicit CORS allowlist
- professional dashboard Control Center
- task search/filter/detail/event surfaces
- agent/worker/monitoring/diagnostic surfaces
- explicit unavailable-capability states instead of fake data
- responsive dashboard layout and accessibility foundations
- production CI for backend, frontend build and served dashboard JavaScript

## Final local synchronization

When PC access is available:

```powershell
cd D:\AI_Workspace\AI-Agent-Platform
git fetch origin
git status
git log --oneline -1
git pull --ff-only origin main
```

If the local branch contains intentional commits that are not on `origin/main`, do not use a destructive reset blindly. Preserve a backup branch first and reconcile deliberately.

## Final validation

Run the repository gates:

```powershell
python -m pytest -q
python scripts/production_gate.py
```

Then validate the real PC Worker:

```powershell
python -m uvicorn worker_system.worker:app --host 0.0.0.0 --port 8001 --log-level info
```

The controller must be configured to reach the worker using the existing `.env`/worker configuration. Ollama must be reachable from the Worker host.

## Real execution smoke test

Submit one small coding task from the dashboard and verify the authoritative lifecycle:

```text
queued → running → completed
```

For a deliberate failure test, verify:

```text
queued → running → failed
```

and confirm that the stored error contains the real Worker/Agent error rather than only a generic HTTP status.

For a failed task, the explicit retry action must produce:

```text
failed → queued
```

without allowing arbitrary lifecycle mutation.

## Dashboard acceptance

Verify:

- `/dashboard` loads without a server-side frontend dependency.
- Overview uses real API state.
- Tasks can be created and inspected.
- Task events are visible.
- Cancellation respects lifecycle rules.
- Failed tasks expose their real error and retry operation when permitted.
- Agent status reflects the actual runtime/Worker connection.
- Worker page does not invent workers or metrics.
- Logs/Models/Tools/Projects show explicit unavailable states until real backend contracts exist.
- No browser-side filesystem or arbitrary terminal execution exists.
- Mobile navigation works.
- RTL Persian layout remains usable.
- No fake production metrics are introduced.

## Important boundary

A repository/CI pass does not prove that the physical PC Worker, Ollama installation, firewall, local network route, environment variables or installed toolchain are correct. Those are intentionally validated only after synchronization on the actual machine.

Likewise, a local smoke-test failure does not justify weakening the execution contract. Fix the root cause while preserving:

1. real execution,
2. observable verification,
3. lifecycle integrity,
4. workspace containment,
5. bounded execution,
6. real error propagation.

## Definition of release handoff

The repository is ready for the final PC validation phase when GitHub CI is green and the codebase contains no known intentional placeholder that pretends an unavailable capability is real.

The final PC phase is validation and root-cause correction, not a rewrite of the architecture.
