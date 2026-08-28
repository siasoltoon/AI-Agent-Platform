from collections import deque

class TaskQueue:
    def __init__(self):
        self.queue = deque()

    def add(self, task):
        self.queue.append(task)

    def get_next(self):
        if self.queue:
            return self.queue.popleft()
        return None
