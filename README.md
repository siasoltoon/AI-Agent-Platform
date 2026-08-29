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

## Production configuration

Copy `.env.example` to `.env` and set deployment-specific values. The API supports explicit `ENVIRONMENT`, `API_HOST`, `API_PORT`, `CORS_ORIGINS` and `LOG_LEVEL` settings. Wildcard CORS is rejected by configuration validation so production deployments must declare their trusted browser origins.

The current architecture keeps heavy agent execution on the configured PC worker. The controller remains responsible for task contracts, routing, persistence, durable task lifecycle and health endpoints.

## Health endpoints

- `GET /health/live` — process liveness.
- `GET /health/ready` — durable task-store readiness.
- `GET /` — backward-compatible service status.

## Validation

Run the full test suite before deployment:

```text
python -m pytest -q
```

Also compile the production execution modules with `python -m py_compile` as documented in `docs/FINAL_PRODUCTION_AUDIT.md`.
