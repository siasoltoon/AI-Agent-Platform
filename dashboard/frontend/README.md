# Dashboard Frontend

Production-oriented React/Vite source for the AI-Agent-Platform Control Center.

## Responsibilities

The frontend is a control-plane UI. It does not implement agent execution, filesystem access or terminal execution. It consumes the Backend as the source of truth and uses the existing task, dashboard and worker contracts.

## Current surface

- Overview / Command Center
- Tasks with search, filtering and real task actions
- Agent runtime status
- Worker monitoring and reported telemetry
- Execution history
- Persisted execution activity/log view
- System monitoring
- Runtime model information when actually reported
- Backend-enforced tool capability surface
- Diagnostics
- Local theme/language settings
- Persian RTL and English LTR
- Desktop/tablet/mobile responsive layouts

## API boundary

All HTTP requests go through `src/api/client.js`. Domain endpoints remain in `src/api/tasks.js` and `src/api/dashboard.js`. No component creates ad-hoc fetch calls.

## Truthfulness rule

Never add fake data to make a page look complete. When a backend capability is not exposed, the UI must say so. Never expose secrets, arbitrary filesystem operations or arbitrary command execution from the browser.

## Run

```text
npm install
npm run dev
```

Production build:

```text
npm run build
```

The repository backend tests and production gate remain the authoritative backend acceptance checks. Frontend build/browser validation should be run when the PC environment is available.
