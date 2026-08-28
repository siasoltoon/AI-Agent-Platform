class RepositoryManager:
    def __init__(self, path: str):
        self.path = path

    def status(self):
        return {"repository": self.path, "status": "unknown"}
