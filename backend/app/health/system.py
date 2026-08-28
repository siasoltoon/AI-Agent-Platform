"""System health checks."""


def health_status() -> dict:
    return {
        "status": "healthy",
        "service": "ai-agent-platform",
    }
