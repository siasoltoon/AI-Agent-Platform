class AgentMessage:
    def __init__(self, sender, receiver, content):
        self.sender = sender
        self.receiver = receiver
        self.content = content


class CommunicationBus:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)

    def history(self):
        return self.messages
