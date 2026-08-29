# AI Agent Platform Dashboard

Professional Control Center for the controller, task engine, agent runtime and workers.

## Production surface

The backend serves the lightweight production dashboard at `/dashboard`. It is intentionally dependency-light and consumes the real REST API exposed by the controller.

## Principles

- Backend is the source of truth.
- No fake metrics, workers, models, tools or logs.
- No browser-side filesystem or terminal execution.
- Task creation and cancellation use the canonical backend contract.
- REST polling is used for current state; real-time streaming is only claimed when an event contract is available.
- The interface is responsive and designed for long-running operations work.

See `docs/dashboard-architecture.md` for the integration and security model.
