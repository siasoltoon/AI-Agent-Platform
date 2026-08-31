# AI Agent Platform — Final Hardening Plan

## Purpose
This document defines the final integration-hardening baseline for the AI Agent Platform before the local PC synchronization pass.

## Non-negotiable architecture
- Backend remains the source of truth.
- Dashboard is a control-plane client and never owns agent execution logic.
- PC Worker remains the execution boundary for local filesystem/terminal work.
- Agent Runtime must preserve observable execution and evidence.
- Task lifecycle transitions must be explicit and validated.
- Retry is a controlled lifecycle operation, not an implicit state mutation.
- No fake data, fake streaming, fake worker state, or fabricated capabilities.
- Secrets and arbitrary filesystem/command access must never be exposed by the Dashboard.

## Final integration areas
1. Task lifecycle and retry semantics
2. Worker execution/error propagation
3. Dashboard API boundary and domain modules
4. Execution/evidence visibility
5. Real-time event/log readiness without pretending unsupported streaming exists
6. Health/diagnostics aggregation
7. Frontend route and state isolation
8. Security boundaries and configuration hygiene
9. Production validation and documentation

## Local validation after synchronization
```powershell
cd D:\AI_Workspace\AI-Agent-Platform
python -m pytest -q
python scripts/production_gate.py
```

Then run the frontend's real production build command from its package manifest.

## Completion rule
A feature is complete only when its implementation, API boundary, error path, tests, documentation, and production behavior are consistent. Local-only failures discovered after synchronization should be fixed against the exact synchronized commit rather than masking them remotely.
