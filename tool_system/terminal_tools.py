import subprocess
from .base_tool import BaseTool


class TerminalTool(BaseTool):
    name = "terminal"

    def execute(self, command):
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "code": result.returncode,
        }
