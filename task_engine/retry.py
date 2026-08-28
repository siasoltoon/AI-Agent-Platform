class RetryPolicy:
    def __init__(self, max_retries=3):
        self.max_retries = max_retries

    def can_retry(self, attempts):
        return attempts < self.max_retries
