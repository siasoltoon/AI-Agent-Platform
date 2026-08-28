class TaskTimeout:
    def __init__(self, seconds=300):
        self.seconds = seconds

    def exceeded(self, elapsed):
        return elapsed > self.seconds
