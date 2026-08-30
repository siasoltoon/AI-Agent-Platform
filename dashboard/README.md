# AI Agent Platform Dashboard

Professional Control Center for the controller, task engine, agent runtime and workers.

## Production surface

The backend serves the lightweight production dashboard at `/dashboard`. It is dependency-light and consumes the real REST API exposed by the controller.

## Principles

- Backend is the source of truth.
- No fake metrics, workers, models, tools or logs.
- No browser-side filesystem or terminal execution.
- Task creation, cancellation and retry use canonical backend contracts.
- REST polling is used for current state; real-time streaming is not claimed unless an event contract exists.
- API failures remain visible to operators instead of becoming false healthy states.
- The interface is responsive and designed for long-running operations work.

## Development frontend

`dashboard/frontend` contains the React/Vite control-plane implementation and is validated by Production CI. The currently served production page remains the dependency-light static dashboard under `dashboard/`.

## Security boundary

The dashboard is an operator surface, not an execution sandbox. It must never add arbitrary terminal commands, browser filesystem access, secret exposure or worker restriction bypasses.
