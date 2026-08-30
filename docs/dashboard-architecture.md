# Dashboard Architecture

## Purpose

The dashboard is the production Control Plane UI for AI-Agent-Platform. It observes authoritative backend state and sends management actions only through backend API contracts.

## Runtime boundary

```text
Browser Dashboard
      |
      v
Centralized HTTP API client
      |
      v
FastAPI Controller
  |       |       |
Tasks   Agents  Workers
  |       \       /
  +---- Dashboard API
  |
Task Store / Task Runner
  |
Agent Runtime -> PC Worker -> Ollama / tools
```

The browser never executes filesystem or terminal operations directly and never becomes a second agent runtime.

## API-backed capabilities

- `GET /health/live` — process liveness.
- `GET /health/ready` — Task Store readiness.
- `GET /agents/status` — Agent Runtime / worker connectivity status.
- `GET /workers/` — worker registry and reported telemetry.
- `GET /tasks?limit=&status=` — durable task listing.
- `GET /tasks/{task_id}` — authoritative task detail.
- `GET /tasks/{task_id}/events` — persisted execution events.
- `POST /tasks/` — queue a task using the canonical Task Contract.
- `POST /tasks/{task_id}/cancel` — request cancellation where lifecycle rules allow it.
- `POST /tasks/{task_id}/retry` — explicitly requeue a failed task.
- `GET /dashboard/summary` — bounded control-plane snapshot containing task aggregates, event totals, agent status and worker state.
- `GET /dashboard/diagnostics` — explicit backend diagnostics with pass/fail details.

Task aggregates are computed from SQLite rather than browser-side guesses. No synthetic task, worker, model or performance data is generated.

## Frontend architecture

The React source under `dashboard/frontend` uses a dependency-light structure so it can be bundled with Vite without forcing a framework migration. `App.jsx` currently owns composition and presentation state while API boundaries remain separated under `src/api`.

- `src/api/client.js` — centralized HTTP boundary, timeout handling and error normalization.
- `src/api/tasks.js` — task contract endpoints.
- `src/api/dashboard.js` — summary, diagnostics, task events and task controls.
- `src/App.jsx` — shell, hash routing, page composition and UI state.
- `src/styles/global.css` — design tokens, themes, responsive behavior and accessibility states.

The structure is intentionally ready for later extraction into dedicated pages/components when the surface grows further.

## UI structure

Primary sections are Overview, Tasks, Agents, Workers, Executions, Logs, Monitoring, Models, Tools, Diagnostics and Settings. Each section has loading, empty and error behavior appropriate to the data it can actually receive.

The Overview is the command center: task submission, system status, KPI cards, recent executions, worker health, activity and database/backend readiness are visible together.

Task details use a side drawer with lifecycle metadata, persisted events, errors, result payloads and execution evidence. Cancel and retry buttons are shown only when the backend lifecycle contract permits those actions.

Models and Tools are truthful capability surfaces. If the backend does not expose a registry or management contract, the dashboard explicitly says so instead of inventing model inventories, tool controls or telemetry.

## State model

Server state comes from the backend. UI state consists of route, filters, search, drawer visibility, selected task, theme and language. The backend remains the source of truth for task lifecycle and execution state.

The dashboard refreshes the summary and bounded task list on a five-second interval. Individual task details are fetched on demand. Search and filtering operate on the bounded server result and do not create an unbounded client-side data sink.

## Real-time strategy

The current dashboard uses REST polling because that is the stable event surface exposed by the backend. The UI does not claim WebSocket/SSE streaming. The activity and log surfaces display persisted task events currently available through the API and can later adopt an event stream without changing the control-plane boundary.

## Design system

Semantic CSS tokens cover background, panels, borders, text, muted text, accent, success, warning, info and danger states. Dark, light and system themes are supported. Focus states, semantic controls, readable contrast and dialog semantics are included.

## Internationalization

English and Persian are supported. Persian switches the document to RTL; English uses LTR. Dashboard-owned labels are selected from a translation map rather than scattered throughout page markup.

## Responsive behavior

Desktop uses a persistent sidebar. Tablet collapses it to an icon rail. Mobile moves navigation to a fixed bottom bar and keeps tables horizontally scrollable rather than breaking their information hierarchy. Drawers become full-width on small screens.

## Security boundary

- No secrets or tokens are rendered.
- No arbitrary filesystem access is exposed to the browser.
- No arbitrary terminal execution is added to the frontend.
- Backend tool permissions and workspace restrictions remain authoritative.
- Sensitive deployment/security settings are not made editable without a backend contract.

## Testing and release

Backend tests and `scripts/production_gate.py` remain the production acceptance baseline. Frontend production validation must run with the package manager declared by `dashboard/frontend/package.json` (`npm run build`). Browser-level validation should cover navigation, task creation, task detail actions, error states, RTL/LTR, themes and responsive layouts.
