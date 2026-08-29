# Dashboard Architecture

## Purpose

The dashboard is the Control Plane UI for AI-Agent-Platform. It observes authoritative backend state and sends management actions only through backend API contracts.

## Runtime boundary

```text
Browser Dashboard
      |
      v
HTTP API client
      |
      v
FastAPI Controller
  |       |       |
Tasks   Agents  Workers
  |
Task Store / Task Runner
  |
Agent Runtime -> PC Worker -> Ollama / tools
```

The browser never executes filesystem or terminal operations directly and never becomes a second agent runtime.

## Current API-backed capabilities

- `GET /health/live` — process liveness.
- `GET /health/ready` — Task Store readiness.
- `GET /agents/status` — Agent Runtime / worker connectivity status.
- `GET /workers/` — worker registry surface (currently empty until the backend registry publishes workers).
- `GET /tasks?limit=&status=` — durable task listing.
- `GET /tasks/{task_id}` — authoritative task detail.
- `GET /tasks/{task_id}/events` — execution events.
- `POST /tasks/` — queue a task using the canonical Task Contract.
- `POST /tasks/{task_id}/cancel` — request cancellation where lifecycle rules allow it.

## UI structure

The production `/dashboard` surface uses a dependency-light operations console with hash routing so the controller remains deployable without a frontend server. The React source under `dashboard/frontend` remains the extensible component architecture for a future bundled deployment.

Primary sections:

- Overview / Command Center
- Tasks
- Agents
- Workers
- Executions
- Logs
- Monitoring
- Models
- Tools
- Projects / Workspaces
- Diagnostics
- Settings

Unavailable backend domains are explicitly marked as not exposed instead of being represented with fabricated data.

## State model

Server state is refreshed from backend APIs. UI state consists of route, filters, modal visibility, selected task and presentation preferences. The backend is always the source of truth for task lifecycle and execution state.

## Real-time strategy

The dashboard currently uses bounded polling for broadly available REST state. The existing WebSocket boundary can be connected when a stable event contract is exposed. The UI must never claim streaming when the backend does not provide it.

## Security

- No secrets or tokens are rendered.
- No arbitrary filesystem access is exposed to the browser.
- No arbitrary terminal execution is added to the frontend.
- Protected server configuration is read-only until an authenticated backend contract exists.

## Responsive and accessibility goals

The layout supports desktop, tablet and mobile widths, including a mobile navigation drawer, visible keyboard focus, semantic controls, labels and dialog semantics.

## Testing

Backend tests and `scripts/production_gate.py` remain the production acceptance baseline. Frontend production validation should run with the package manager declared by `dashboard/frontend/package.json` (`npm run build`) when a bundled frontend is deployed.
