# Production Deployment Baseline

This document defines the application-level deployment baseline for the current PC-worker architecture.

## Required environment

Set these values explicitly in the deployment environment:

- `ENVIRONMENT=production`
- `API_HOST`
- `API_PORT`
- `CORS_ORIGINS` as a comma-separated allowlist of trusted origins
- `LOG_LEVEL`
- Worker/Ollama settings from `.env.example`
- `TASK_DB_PATH` pointing to durable storage

Do not commit `.env` or real secrets.

## Network boundary

The controller API and PC worker should be reachable only from the networks that require them. The worker port should not be exposed to the public internet.

TLS termination, firewall policy and reverse-proxy configuration are deployment responsibilities and must be supplied by the operator.

## Process supervision

Run the backend and PC worker under a process supervisor appropriate to the host. Configure automatic restart, stdout/stderr capture and a bounded shutdown grace period.

## Health checks

Use `GET /health/live` for liveness and `GET /health/ready` for readiness. A load balancer or process supervisor should remove an instance from service when readiness fails.

## Persistence

Back up the SQLite file referenced by `TASK_DB_PATH` when task history is operationally important. Do not place the database on ephemeral deployment storage.

## Validation gate

Before deployment:

```text
python -m pytest -q
```

The release is not considered production-ready if tests fail, task execution returns a suggestion instead of performing the task, or execution completion lacks observable evidence.
