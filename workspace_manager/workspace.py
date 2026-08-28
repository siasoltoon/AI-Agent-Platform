from pathlib import Path


class Workspace:
    def __init__(self, root: str):
        self.root = Path(root)

    def exists(self) -> bool:
        return self.root.exists()

    def list_files(self):
        if not self.exists():
            return []
        return [str(p) for p in self.root.rglob('*') if p.is_file()]
