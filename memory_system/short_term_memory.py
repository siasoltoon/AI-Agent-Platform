class ShortTermMemory:
    def __init__(self):
        self.context = []

    def add(self, value):
        self.context.append(value)

    def get(self):
        return self.context
