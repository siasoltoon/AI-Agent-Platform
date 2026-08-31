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

The agent is considered complete only after real tool execution and observable verification evidence. It does not treat model-generated suggested code as task completion.

The reliable execution layer now gives each worker execution a bounded six-attempt self-repair budget. A recovery attempt receives the original mission, the previous failure and recent tool observations, then continues from the existing workspace instead of restarting blindly. Durable task retries are also bounded at five retries, so transient worker/model failures can recover without requiring the user to resubmit the task.

## Live worker telemetry

The PC worker exposes a live resource snapshot from `GET /health`, including CPU percentage, RAM percentage/usage and GPU percentage when the host operating system provides a GPU utilization provider. CPU/RAM telemetry uses `psutil`; GPU telemetry prefers `nvidia-smi` and falls back to Windows GPU Engine performance counters, including support for AMD/Intel adapters. The dashboard polls `GET /workers/` every second and keeps a dedicated `Worker health` panel visible before, during and after task execution.

## Production configuration

Copy `.env.example` to `.env` and set deployment-specific values. The API supports explicit `ENVIRONMENT`, `API_HOST`, `API_PORT`, `CORS_ORIGINS` and `LOG_LEVEL` settings. Wildcard CORS is rejected by configuration validation so production deployments must declare their trusted browser origins.

The current architecture keeps heavy agent execution on the configured PC worker. The controller remains responsible for task contracts, routing, persistence, durable task lifecycle and health endpoints.

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
