"""API Gateway foundation.

Provides a central entry point for future dashboard and agent communication.
"""

class APIGateway:
    def __init__(self):
        self.routes = {}

    def register(self, name, handler):
        self.routes[name] = handler

    def get_routes(self):
        return self.routes
