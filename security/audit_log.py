class AuditLog:
    def __init__(self):
        self.events = []

    def record(self, event):
        self.events.append(event)

    def get_events(self):
        return self.events
