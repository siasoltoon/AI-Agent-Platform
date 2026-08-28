class AgentManager:
    def __init__(self, registry):
        self.registry = registry

    def add_agent(self, name, agent):
        self.registry.register(name, agent)

    def get_agent(self, name):
        return self.registry.get(name)
