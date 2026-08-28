"""Planner agent foundation."""

class PlannerAgent:
    name = "planner"

    def plan(self, task):
        return {
            "task": task,
            "steps": [],
            "status": "planned"
        }
