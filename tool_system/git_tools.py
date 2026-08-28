from .base_tool import BaseTool


class GitStatusTool(BaseTool):
    name = "git_status"

    def execute(self, command="git status"):
        return command
