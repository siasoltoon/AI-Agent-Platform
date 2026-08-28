class OllamaClient:
    def __init__(self, host="http://localhost:11434", model="qwen2.5-coder:7b"):
        self.host = host
        self.model = model

    def generate(self, prompt):
        return {
            "model": self.model,
            "prompt": prompt,
            "status": "ready"
        }
