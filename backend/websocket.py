"""WebSocket event stream foundation."""

class EventStream:
    def __init__(self):
        self.listeners = []

    def subscribe(self, callback):
        self.listeners.append(callback)

    def publish(self, event):
        for callback in self.listeners:
            callback(event)
