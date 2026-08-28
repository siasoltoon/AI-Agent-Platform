class Sandbox:
    def __init__(self, workspace):
        self.workspace = workspace

    def validate_path(self, path):
        return str(path).startswith(str(self.workspace))
