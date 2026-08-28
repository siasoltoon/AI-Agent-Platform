class ContextBuilder:
    def build(self, task, project_context):
        return {
            "task": task,
            "context": project_context
        }
