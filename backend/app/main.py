from fastapi import FastAPI

app = FastAPI(
    title="AI Agent Platform API",
    version="1.0.0"
)

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "backend"
    }
