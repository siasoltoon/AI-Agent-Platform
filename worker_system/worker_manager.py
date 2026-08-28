class WorkerManager:
    def __init__(self):
        self.workers = {}

    def register(self, worker):
        self.workers[worker.worker_id] = worker

    def get_worker(self, worker_id):
        return self.workers.get(worker_id)
