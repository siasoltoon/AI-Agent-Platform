# AI-Agent-Platform

A modular local AI agent platform for managing tasks, tools, workspaces and automation.

## Core Modules
- Agent Core
- Task Engine
- Tool System
- Workspace Manager
- Git Manager
- Test Engine
- Dashboard
- Backend

## Production execution guarantees

The controller uses the canonical Task Contract and routes `agent.execute` tasks to the real agentic execution path. Tasks are persisted in SQLite so lifecycle state survives backend restarts, and the backend exposes liveness/readiness probes for deployment health checks.

Task submission is asynchronous: the API persists a task as `queued`, the durable background runner claims it, executes it through the real agent/PC worker path, and persists `completed` or `failed` evidence. The dashboard polls the task endpoint so the user can observe the real lifecycle without keeping the HTTP request open.

The agent is considered complete only after real tool execution, observable evidence and independent verification. It does not treat model-generated suggested code as task completion.

Each execution is protected by a durable execution ID and monotonic fencing token. Completion is committed atomically through the execution ledger, so stale workers cannot publish completion after a newer attempt takes ownership. Recovery can reconcile a durable committed attempt after restart without replaying the agent.

Mutation-capable tools use a durable side-effect ledger with task-scoped idempotency keys, request-hash validation and ownership fencing. Committed results can be replayed idempotently; ambiguous and failed side effects are never blindly replayed.

For remote PC workers, execution authority remains on the controller. The remote worker entrypoint `worker_system.remote_worker` proxies fence checks and the durable side-effect ledger to the controller over HTTP, so the worker does not depend on a local copy of `data/tasks.db` for authoritative fencing.

The reliable execution layer gives each worker execution a bounded six-attempt self-repair budget. A recovery attempt receives the original mission, the previous failure and recent tool observations, then continues from the existing workspace instead of restarting blindly. Durable task retries are also bounded at five retries, so transient worker/model failures can recover without requiring the user to resubmit the task.

## Live worker telemetry

The PC worker exposes a live resource snapshot from `GET /health`, including CPU percentage, RAM percentage/usage and GPU percentage when the host operating system provides a GPU utilization provider. CPU/RAM telemetry uses `psutil`; GPU telemetry prefers `nvidia-smi` and falls back to Windows GPU Engine performance counters, including support for AMD/Intel adapters. The dashboard polls `GET /workers/` every second and keeps a dedicated `Worker health` panel visible before, during and after task execution.

## Production configuration

Copy `.env.example` to `.env` and set deployment-specific values. Wildcard CORS is rejected by configuration validation so production deployments must declare their trusted browser origins.

The current architecture keeps heavy agent execution on the configured PC worker. The controller remains responsible for task contracts, routing, persistence, durable task lifecycle, execution authority and health endpoints.

For a remote PC worker, set `EXECUTION_AUTHORITY_URL` to the controller's LAN URL, for example `http://192.168.1.2:8000`, and run:

```text
python -m uvicorn worker_system.remote_worker:app --host 0.0.0.0 --port 8001
```

If `EXECUTION_AUTHORITY_TOKEN` is set, configure the same secret on both controller and worker. Keep the controller's port reachable from the worker but do not expose the internal execution-authority endpoints publicly.

## Health endpoints

- `GET /health/live` — process liveness.
- `GET /health/ready` — durable task-store readiness.
- `GET /` — backward-compatible service status.
- `GET /workers/` — configured worker status plus live CPU/RAM/GPU telemetry.
- `GET http://<worker-host>:<worker-port>/health` — direct worker health and telemetry.

## Validation

Run the deterministic production gate from the repository root:

```text
python scripts/production_gate.py
```

Run the full test suite explicitly when needed:

```text
python -m pytest -q
```

Build the frontend using the script declared by `dashboard/frontend/package.json`:

```text
cd dashboard/frontend
npm install
npm run build
```

The repository gate intentionally does not claim live PC-worker/Ollama execution. That environment-dependent acceptance test must be performed after synchronizing the exact hardening branch to the PC.

## Final production readiness

The complete execution/recovery boundary and acceptance checklist is documented in `docs/FINAL_PRODUCTION_READINESS.md`. The final audit also covers the execution fence, durable execution ledger, side-effect ledger, recovery sweep and safe task runner.
