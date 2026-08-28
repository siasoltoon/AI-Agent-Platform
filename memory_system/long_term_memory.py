class LongTermMemory:
    def __init__(self):
        self.records = []

    def store(self, record):
        self.records.append(record)

    def search(self, keyword):
        return [r for r in self.records if keyword in str(r)]
