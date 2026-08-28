class DuplicateGuard:
    """Prevents duplicate task execution."""

    def __init__(self):
        self._seen = set()

    def is_duplicate(self, task_id):
        return task_id in self._seen

    def register(self, task_id):
        self._seen.add(task_id)

    def clear(self, task_id=None):
        if task_id is None:
            self._seen.clear()
        else:
            self._seen.discard(task_id)
