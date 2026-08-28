class FileTracker:
    def __init__(self):
        self.changes = []

    def track(self, file_path: str, action: str):
        self.changes.append({"file": file_path, "action": action})

    def history(self):
        return self.changes
