class AgentExecutor:
    def __init__(self, tool_manager=None):
        self.tool_manager = tool_manager

    def execute(self, plan):
        return {
            "status": "completed",
            "plan": plan
        }
