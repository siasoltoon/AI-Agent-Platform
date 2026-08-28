class TaskScheduler:
    def __init__(self, queue):
        self.queue = queue

    def run_next(self):
        task = self.queue.pop()
        return task
