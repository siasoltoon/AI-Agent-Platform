class Planner:
    def create_plan(self, task):
        return {
            "task_id": task.get("task_id"),
            "steps": [],
            "status": "planned"
        }
