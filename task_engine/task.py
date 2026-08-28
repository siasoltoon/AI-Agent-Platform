from dataclasses import dataclass
from datetime import datetime

@dataclass
class Task:
    task_id: str
    description: str
    status: str = "queued"
    created_at: str = datetime.utcnow().isoformat()
