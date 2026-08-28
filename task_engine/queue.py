from collections import deque

class TaskQueue:
    def __init__(self):
        self.queue = deque()

    def add(self, task):
        self.queue.append(task)

    def get_next(self):
        return self.queue.popleft() if self.queue else None

    def size(self):
        return len(self.queue)
