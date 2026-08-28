"""Agent memory foundation."""

class AgentMemory:
    def __init__(self):
        self.history = []

    def remember(self, item):
        self.history.append(item)

    def get_history(self):
        return self.history
