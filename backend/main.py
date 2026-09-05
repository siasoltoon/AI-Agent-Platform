"""
AI Agent Platform Backend

Main FastAPI application.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.api import agents
from backend.api import dashboard
from backend.api import tasks
from backend.api import workers
from backend.recovery_sweep import RecoverySweep
from backend.safe_task_runner import SafeTaskRunner
from backend.storage.execution_ledger import ExecutionLedger
from backend.storage.worker_lease_store import WorkerLeaseStore
from backend.task_runner import DEFAULT_POLL_SECONDS
from config.production_config import CONFIG

BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = BASE_DIR / "dashboard"


@asynccontextmanager
async def lifespan(_: FastAPI):
    lease_store = WorkerLeaseStore(tasks.TASK_STORE.path)
    execution_ledger = ExecutionLedger(tasks.TASK_STORE.path)
    recovery_sweep = RecoverySweep(
        tasks.TASK_STORE,
        lease_store,
        reconciler=tasks.mission_service.reconciler,
        execution_ledger=execution_ledger,
    )
    runner = SafeTaskRunner(
        tasks.TASK_STORE,
        tasks.task_router,
        poll_seconds=DEFAULT_POLL_SECONDS,
        shutdown_timeout_seconds=CONFIG.shutdown_timeout_seconds,
        lease_store=lease_store,
        recovery_sweep=recovery_sweep,
        execution_ledger=execution_ledger,
    )
    tasks.TASK_RUNNER = runner
    runner.start()
    try:
        yield
    finally:
        runner.stop(timeout_seconds=CONFIG.shutdown_timeout_seconds)
        tasks.TASK_RUNNER = None


app = FastAPI(
    title="AI-Agent-Platform",
    version="0.1.0",
    description="AI Agent Platform Controller",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CONFIG.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(tasks.router)
app.include_router(agents.router)
app.include_router(workers.router)
app.include_router(dashboard.router)


@app.get("/")
async def health() -> dict:
    """Backward-compatible service health endpoint."""
    runner = tasks.TASK_RUNNER
    return {
        "status": "running",
        "service": "AI-Agent-Platform",
        "version": app.version,
        "environment": CONFIG.environment,
        "runner": "running" if runner is not None and runner.running else "stopped",
    }


@app.get("/health/live", tags=["Health"])
async def liveness() -> dict:
    """Process-level liveness probe: no dependency checks are required."""
    return {
        "status": "ok",
        "service": app.title,
        "version": app.version,
        "environment": CONFIG.environment,
    }


@app.get("/health/ready", tags=["Health"])
async def readiness() -> dict:
    """Readiness probe verifies durable storage and the background runner."""
    checks = {}
    try:
        storage_ready = tasks.TASK_STORE.ping()
    except Exception:
        storage_ready = False
    checks["task_store"] = "ok" if storage_ready else "failed"

    runner = tasks.TASK_RUNNER
    runner_ready = runner is not None and runner.running
    checks["task_runner"] = "ok" if runner_ready else "failed"

    ready = storage_ready and runner_ready
    return {
        "status": "ready" if ready else "not_ready",
        "service": app.title,
        "version": app.version,
        "environment": CONFIG.environment,
        "checks": checks,
    }


@app.get("/dashboard", include_in_schema=False)
async def dashboard_page():
    index_file = DASHBOARD_DIR / "index.html"
    if not index_file.exists():
        return {"status": "error", "message": "Dashboard index.html not found."}
    return FileResponse(index_file, headers={"Cache-Control": "no-store"})


@app.get("/dashboard/style.css", include_in_schema=False)
async def dashboard_css():
    css_file = DASHBOARD_DIR / "style.css"
    if not css_file.exists():
        return {"status": "error", "message": "Dashboard style.css not found."}
    return FileResponse(css_file, media_type="text/css")


@app.get("/dashboard/app.js", include_in_schema=False)
async def dashboard_js():
    js_file = DASHBOARD_DIR / "app.js"
    if not js_file.exists():
        return {"status": "error", "message": "Dashboard app.js not found."}
    return FileResponse(
        js_file,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/tasks/", include_in_schema=False)
async def dashboard_task_list() -> dict:
    """Compatibility endpoint for the dashboard's exact GET /tasks/ request."""
    return {"tasks": tasks.TASK_STORE.list()}
