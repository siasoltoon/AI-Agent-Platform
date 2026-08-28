class JobQueue:
    def __init__(self):
        self.jobs = []

    def add(self, job):
        self.jobs.append(job)

    def get_next(self):
        if not self.jobs:
            return None
        return self.jobs.pop(0)
