from datetime import datetime


class TaskHistory:
    """Stores task execution history."""

    def __init__(self):
        self.records = []

    def add(self, task_id, status, metadata=None):
        self.records.append({
            "task_id": task_id,
            "status": status,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        })

    def get_all(self):
        return self.records

    def get(self, task_id):
        return [r for r in self.records if r["task_id"] == task_id]
