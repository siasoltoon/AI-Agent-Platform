"""Agent manager foundation."""

class AgentManager:
    def __init__(self):
        self.agents = {}

    def register(self, name, agent):
        self.agents[name] = agent

    def get(self, name):
        return self.agents.get(name)

    def status(self):
        return {name: "ready" for name in self.agents}
