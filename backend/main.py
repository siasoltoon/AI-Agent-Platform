"""
AI Agent Platform Backend

Main FastAPI application.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.api import agents
from backend.api import tasks
from config.production_config import CONFIG


BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = BASE_DIR / "dashboard"


app = FastAPI(
    title="AI-Agent-Platform",
    version="0.1.0",
    description="AI Agent Platform Controller",
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


@app.get("/")
async def health() -> dict:
    """Backward-compatible service health endpoint."""
    return {
        "status": "running",
        "service": "AI-Agent-Platform",
        "version": app.version,
        "environment": CONFIG.environment,
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
    """Readiness probe that verifies the durable task store is reachable."""
    try:
        storage_ready = tasks.TASK_STORE.ping()
    except Exception:
        return {
            "status": "not_ready",
            "service": app.title,
            "version": app.version,
            "checks": {"task_store": "failed"},
        }

    return {
        "status": "ready" if storage_ready else "not_ready",
        "service": app.title,
        "version": app.version,
        "checks": {"task_store": "ok" if storage_ready else "failed"},
    }


@app.get("/dashboard", include_in_schema=False)
async def dashboard():
    index_file = DASHBOARD_DIR / "index.html"
    if not index_file.exists():
        return {"status": "error", "message": "Dashboard index.html not found."}
    return FileResponse(index_file)


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
    return FileResponse(js_file, media_type="application/javascript")
