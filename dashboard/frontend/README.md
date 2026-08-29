# Dashboard Frontend Source

This directory contains the extensible React source architecture for the AI Agent Platform dashboard.

The controller's currently served production surface is the dependency-light `/dashboard` application. The React source is kept aligned as the component-oriented evolution path and can be bundled with Vite when the deployment contract requires a separate frontend artifact.

Current package scripts: `npm run dev`, `npm run build`.

Do not add fake API data to make UI states look complete. Components must consume backend contracts and explicitly represent unavailable capabilities.
