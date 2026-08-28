"""Coder agent foundation."""

class CoderAgent:
    name = "coder"

    def execute(self, plan):
        return {"status": "ready", "plan": plan}
