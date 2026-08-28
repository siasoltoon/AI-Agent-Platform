class Worker:
    def __init__(self, worker_id):
        self.worker_id = worker_id
        self.status = "idle"

    def execute(self, job):
        self.status = "running"
        result = {"job": job, "status": "completed"}
        self.status = "idle"
        return result
