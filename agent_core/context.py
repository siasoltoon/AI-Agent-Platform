class ContextManager:
    def __init__(self):
        self.context = {}

    def set(self, key, value):
        self.context[key] = value

    def get(self, key, default=None):
        return self.context.get(key, default)

    def update(self, values):
        self.context.update(values)

    def clear(self):
        self.context.clear()
