"""Database models foundation."""

class TaskRecord:
    def __init__(self, task_id, status="pending"):
        self.task_id = task_id
        self.status = status


class AgentRecord:
    def __init__(self, agent_id, role):
        self.agent_id = agent_id
        self.role = role
