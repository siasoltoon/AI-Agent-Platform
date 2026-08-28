class MemoryStorage:
    def __init__(self):
        self.data = []

    def save(self, item):
        self.data.append(item)

    def all(self):
        return self.data
