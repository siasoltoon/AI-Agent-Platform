from fastapi import FastAPI

app = FastAPI(title="AI-Agent-Platform")

@app.get("/")
def health():
    return {"status": "running", "service": "backend"}
