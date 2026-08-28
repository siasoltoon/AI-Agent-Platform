"""
AI Agent Platform Backend

Main FastAPI Application
"""

from fastapi import FastAPI

from backend.api import tasks
from backend.api import agents


app = FastAPI(
    title="AI-Agent-Platform",
    version="0.1.0",
    description="Local AI Agent Runtime Platform"
)


# Register APIs

app.include_router(
    tasks.router
)


app.include_router(
    agents.router
)



@app.get("/")
async def health():

    return {

        "status": "running",

        "service": "AI-Agent-Platform",

        "modules": [

            "task_api",

            "agent_api",

            "ollama_ready"

        ]

    }
