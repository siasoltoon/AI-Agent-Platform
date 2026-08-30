# Final Sync Checklist

## Before synchronization
- Keep the remote `main` history as the integration source.
- Do not overwrite local work blindly.
- Preserve any local untracked agent test artifacts separately.

## After synchronization
Run:

```powershell
cd D:\AI_Workspace\AI-Agent-Platform
python -m pytest -q
python scripts/production_gate.py
```

Run the frontend production build using the package manager and script declared by the frontend package manifest.

## If local validation fails
- Capture the complete error output.
- Identify whether the failure is environment-specific or a real regression.
- Fix the root cause.
- Re-run the failing validation and the full suite.
- Never suppress or fabricate a passing result.

## Dashboard acceptance
- Routes load without fatal errors.
- Backend remains the source of truth.
- Task/agent/worker/execution data is real.
- Unsupported operations are not presented as functional controls.
- RTL/LTR and theme switching remain consistent.
- Loading, empty, and error states are present.
- Production build succeeds.
