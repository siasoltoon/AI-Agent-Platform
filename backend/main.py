"""
AI Agent Platform Backend

Main FastAPI application.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.api import tasks
from backend.api import agents


BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = BASE_DIR / "dashboard"


app = FastAPI(
    title="AI-Agent-Platform",
    version="0.1.0",
    description="AI Agent Platform Controller",
)


# -------------------------------------------------------------------
# CORS
# -------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------------
# API Routers
# -------------------------------------------------------------------

app.include_router(
    tasks.router
)

app.include_router(
    agents.router
)


# -------------------------------------------------------------------
# Health
# -------------------------------------------------------------------

@app.get("/")
async def health():
    return {
        "status": "running",
        "service": "AI-Agent-Platform",
        "version": "0.1.0",
    }


# -------------------------------------------------------------------
# Dashboard
# -------------------------------------------------------------------

@app.get(
    "/dashboard",
    include_in_schema=False,
)
async def dashboard():

    index_file = DASHBOARD_DIR / "index.html"

    if not index_file.exists():

        return {
            "status": "error",
            "message": "Dashboard index.html not found.",
        }

    return FileResponse(
        index_file
    )
